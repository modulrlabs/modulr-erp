import urllib.parse
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from core.audit import log_audit_event
from core.mixins import validate_tenant_fk
from core.models import ShopSettings, User
from core.rbac import get_request_permissions
from inventory.models import Product, StockMovement

from .models import (
    CreditPayment,
    Customer,
    Invoice,
    InvoiceItem,
    PDCheque,
    SalesReturn,
    SalesReturnItem,
)


class CustomerSerializer(serializers.ModelSerializer):
    """
    Serializer for Customer details and Credit Ledger balance.
    """
    class Meta:
        model = Customer
        fields = (
            'id',
            'public_id',
            'name',
            'phone',
            'address',
            'total_credit_balance',
            'created_at',
            'updated_at',
        )
        # WHY total_credit_balance is read_only:
        # A user must NEVER directly overwrite a customer's credit balance via PUT/PATCH!
        # Balance must ONLY change via authenticated sales (invoices) or audited credit settlements.
        read_only_fields = ('id', 'public_id', 'total_credit_balance', 'created_at', 'updated_at')


class InvoiceItemSerializer(serializers.ModelSerializer):
    """
    Serializer for line items within an invoice.
    """
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = InvoiceItem
        fields = (
            'id',
            'product',
            'product_name',
            'quantity',
            'unit_price',
            'cost_price_at_sale',
            'line_total',
        )
        read_only_fields = ('id', 'product_name', 'unit_price', 'cost_price_at_sale', 'line_total')

    def __init__(self, *args, **kwargs):
        """
        WHY: Maintain security consistency.
        Cashiers must not see wholesale cost price snapshots.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and 'inventory.view_cost_price' not in get_request_permissions(request):
            self.fields.pop('cost_price_at_sale', None)


class InvoiceItemInputSerializer(serializers.Serializer):
    """
    Input serializer for each item being rung up at checkout.
    Supports fractional quantities (e.g., 1.250 kg).
    """
    product_id = serializers.IntegerField(required=True)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=True,
        min_value=Decimal('0.001')
    )


class InvoiceCheckoutSerializer(serializers.Serializer):
    """
    Handles Atomic POS Checkout: POST /api/sales/invoices/

    WHY:
    A POS sale involves 5 distinct, interdependent database actions:
    1. Stock check & deduction with select_for_update() row locks.
    2. Generating the invoice header with auto-sequenced numbering.
    3. Creating line items with cost-price snapshots.
    4. Recording immutable StockMovement ledger entries.
    5. Updating customer debt ledger if payment is credit / pay-later.
    All 5 MUST execute inside transaction.atomic() to guarantee financial integrity.
    """
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True,
        default=None,
        help_text="Customer ID. Required only if payment involves store credit."
    )
    payment_method = serializers.ChoiceField(
        choices=Invoice.PaymentMethod.choices,
        default=Invoice.PaymentMethod.CASH
    )
    discount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        min_value=Decimal('0.00')
    )
    amount_paid = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=Decimal('0.00'),
        min_value=Decimal('0.00')
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default=""
    )
    items = InvoiceItemInputSerializer(
        many=True,
        allow_empty=False,
        help_text="List of products and quantities purchased."
    )

    def validate_customer(self, value):
        """
        WHY: Prevent Cross-Tenant IDOR attacks (ARCHITECTURE.md Rule B).
        Customer must belong to the active shop.
        """
        request = self.context.get('request')
        shop = getattr(getattr(request, 'user', None), 'shop', None)
        return validate_tenant_fk(value, shop, field_name="customer")

    def create(self, validated_data):
        request = self.context['request']
        shop = request.user.shop
        cashier = request.user

        customer = validated_data.get('customer')
        payment_method = validated_data.get('payment_method')
        discount = validated_data.get('discount', Decimal('0.00'))
        if discount > Decimal('0.00') and 'sales.apply_discount' not in get_request_permissions(request):
            raise PermissionDenied("You do not have permission to apply invoice discounts.")
        amount_paid = validated_data.get('amount_paid', Decimal('0.00'))
        notes = validated_data.get('notes', '')
        idempotency_key = validated_data.get('idempotency_key')
        items_data = validated_data.get('items', [])

        product_ids = [item['product_id'] for item in items_data]
        unique_product_ids = set(product_ids)
        qty_map = {item['product_id']: item['quantity'] for item in items_data}

        # ----------------------------------------------------------------------
        # ATOMIC TRANSACTION BLOCK WITH ROW-LEVEL CONCURRENCY LOCKS
        # ----------------------------------------------------------------------
        with transaction.atomic():
            # WHY select_for_update():
            # In a busy supermarket, two cashiers at register 1 and register 2 might
            # ring up the last carton of milk at the exact same millisecond.
            # select_for_update() places an exclusive PostgreSQL row lock on these product
            # rows until this checkout commits, preventing overselling / race conditions.
            products = list(
                Product.objects.select_for_update()
                .filter(id__in=unique_product_ids, shop=shop, is_deleted=False)
            )

            # Validate that all requested products were found in this tenant
            if len(products) != len(unique_product_ids):
                raise serializers.ValidationError(
                    {"items": "One or more products are invalid or unavailable."}
                )

            # Check stock and calculate subtotal
            subtotal = Decimal('0.00')
            line_items_to_create = []

            for product in products:
                quantity = qty_map[product.id]

                if product.stock_quantity < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for '{product.name}'. "
                        f"Available: {product.stock_quantity}, Requested: {quantity}."
                    )

                # Deduct stock safely
                product.stock_quantity -= quantity
                product.save(update_fields=['stock_quantity', 'updated_at'])

                line_total = (product.selling_price * quantity).quantize(Decimal('0.01'))
                subtotal += line_total

                line_items_to_create.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price': product.selling_price,
                    # WHY snapshot: Cost prices change over time; snapshotting freezes historical profit.
                    'cost_price_at_sale': product.cost_price,
                    'line_total': line_total,
                })

            # Validate discount range & enforce Cashier Discount Cap
            if discount < Decimal('0.00') or discount > subtotal:
                raise serializers.ValidationError({
                    'discount': 'Discount must be between 0.00 and the invoice subtotal.'
                })

            shop_settings = ShopSettings.objects.filter(shop_id=shop.id).first()
            if cashier.role == User.Role.CASHIER:
                max_cap_pct = (
                    shop_settings.cashier_max_discount_pct
                    if shop_settings
                    else Decimal('0.00')
                )
                max_allowed_discount = (
                    subtotal * max_cap_pct / Decimal('100.00')
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if discount > max_allowed_discount:
                    raise serializers.ValidationError({
                        'discount': (
                            f'Discount exceeds the maximum allowed cap of '
                            f'{max_cap_pct}% (Rs. {max_allowed_discount}).'
                        )
                    })

            # Authoritative Tax Calculation (NONE / EXCLUSIVE / INCLUSIVE)
            taxable_base = subtotal - discount
            tax_mode = shop_settings.tax_mode if shop_settings else 'NONE'
            tax_rate_pct = shop_settings.tax_rate_pct if shop_settings else Decimal('0.00')
            tax_label = shop_settings.tax_label if shop_settings else 'VAT'

            if tax_mode == 'EXCLUSIVE':
                tax_amount = (
                    taxable_base * tax_rate_pct / Decimal('100.00')
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                total_amount = taxable_base + tax_amount
            elif tax_mode == 'INCLUSIVE':
                total_amount = taxable_base
                net_amount = taxable_base / (
                    Decimal('1.00') + (tax_rate_pct / Decimal('100.00'))
                )
                tax_amount = (taxable_base - net_amount).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
            else:
                tax_amount = Decimal('0.00')
                total_amount = taxable_base

            # If amount_paid wasn't specified for CASH/CARD, assume fully paid
            is_cash_or_card = payment_method in (Invoice.PaymentMethod.CASH, Invoice.PaymentMethod.CARD)
            if is_cash_or_card and amount_paid == Decimal('0.00'):
                amount_paid = total_amount

            # Calculate remaining credit (debt)
            credit_amount = max(Decimal('0.00'), total_amount - amount_paid)

            # ------------------------------------------------------------------
            # MODULAR FEATURE FLAG CHECK (Credit Module)
            # ------------------------------------------------------------------
            if credit_amount > Decimal('0.00') or payment_method == Invoice.PaymentMethod.CREDIT:
                if not shop.enable_credit_module:
                    raise serializers.ValidationError(
                        "Credit sales are disabled for your shop subscription. "
                        "Payment must cover the full total amount."
                    )
                if not customer:
                    raise serializers.ValidationError(
                        "A registered customer is required when selling on credit (Pay Later)."
                    )

                # Atomically update customer credit ledger
                customer.total_credit_balance += credit_amount
                customer.save(update_fields=['total_credit_balance', 'updated_at'])

            # ------------------------------------------------------------------
            # GENERATE SEQUENTIAL INVOICE NUMBER
            # Format: INV-<YYYYMMDD>-<0001>
            # ------------------------------------------------------------------
            today_str = timezone.now().strftime('%Y%m%d')
            daily_count = Invoice.objects.filter(
                shop=shop,
                created_at__date=timezone.now().date()
            ).count() + 1
            invoice_number = f"INV-{today_str}-{daily_count:04d}"

            # Create Invoice Header
            invoice = Invoice.objects.create(
                shop=shop,
                invoice_number=invoice_number,
                customer=customer,
                cashier=cashier,
                subtotal=subtotal,
                discount=discount,
                tax_mode=tax_mode,
                tax_rate_pct=tax_rate_pct,
                tax_label=tax_label,
                tax_amount=tax_amount,
                total_amount=total_amount,
                payment_method=payment_method,
                amount_paid=amount_paid,
                credit_amount=credit_amount,
                notes=notes,
                idempotency_key=idempotency_key,
            )

            # Create Invoice Line Items and StockMovement ledger records
            for item_data in line_items_to_create:
                InvoiceItem.objects.create(
                    shop=shop,
                    invoice=invoice,
                    product=item_data['product'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    cost_price_at_sale=item_data['cost_price_at_sale'],
                    line_total=item_data['line_total'],
                )
                StockMovement.objects.create(
                    shop=shop,
                    product=item_data['product'],
                    movement_type=StockMovement.MovementType.SALE,
                    quantity_change=-item_data['quantity'],
                    balance_after=item_data['product'].stock_quantity,
                    reference_type='Invoice',
                    reference_id=str(invoice.public_id),
                    notes=f"Sold on invoice {invoice.invoice_number}",
                    performed_by=cashier,
                )

            # Record audit event for invoice creation
            log_audit_event(
                action='INVOICE_CREATED',
                target_model='Invoice',
                target_id=str(invoice.public_id),
                shop=shop,
                actor=cashier,
                after_state={
                    'invoice_number': invoice.invoice_number,
                    'total_amount': invoice.total_amount,
                    'payment_method': invoice.payment_method,
                    'amount_paid': invoice.amount_paid,
                    'credit_amount': invoice.credit_amount,
                    'item_count': len(line_items_to_create),
                }
            )

            # Record audit event if discount was applied
            if discount > Decimal('0.00'):
                log_audit_event(
                    action='DISCOUNT_APPLIED',
                    target_model='Invoice',
                    target_id=str(invoice.public_id),
                    shop=shop,
                    actor=cashier,
                    after_state={
                        'invoice_number': invoice.invoice_number,
                        'subtotal': subtotal,
                        'discount': discount,
                        'total_amount': total_amount,
                    }
                )

            return invoice


class SalesReturnItemSerializer(serializers.ModelSerializer):
    """
    Serializer for line items in a SalesReturn transaction.
    """
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = SalesReturnItem
        fields = (
            'id',
            'public_id',
            'product',
            'product_name',
            'invoice_item',
            'quantity',
            'unit_price',
            'cost_price_at_sale',
            'line_total',
        )
        read_only_fields = fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and 'inventory.view_cost_price' not in get_request_permissions(request):
            self.fields.pop('cost_price_at_sale', None)


class SalesReturnSerializer(serializers.ModelSerializer):
    """
    Serializer for SalesReturn / Credit Note records.
    """
    items = SalesReturnItemSerializer(many=True, read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.username', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)

    class Meta:
        model = SalesReturn
        fields = (
            'id',
            'public_id',
            'return_number',
            'invoice',
            'invoice_number',
            'reason',
            'total_refund_amount',
            'credit_reversed',
            'cash_refunded',
            'processed_by',
            'processed_by_name',
            'items',
            'created_at',
        )
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Detailed read serializer for Invoices, including line items and WhatsApp receipt share link.
    """
    items = InvoiceItemSerializer(many=True, read_only=True)
    returns = SalesReturnSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default="Walk-in Customer")
    customer_phone = serializers.CharField(source='customer.phone', read_only=True, default="")
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    whatsapp_share_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            'id',
            'public_id',
            'invoice_number',
            'status',
            'status_display',
            'customer',
            'customer_name',
            'customer_phone',
            'cashier',
            'cashier_name',
            'subtotal',
            'discount',
            'tax_mode',
            'tax_rate_pct',
            'tax_label',
            'tax_amount',
            'total_amount',
            'payment_method',
            'amount_paid',
            'credit_amount',
            'notes',
            'void_reason',
            'voided_at',
            'voided_by',
            'idempotency_key',
            'items',
            'returns',
            'whatsapp_share_url',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    def get_whatsapp_share_url(self, obj) -> str:
        """
        Generates a direct WhatsApp click-to-chat URL with an automated receipt text:
        https://wa.me/<phone>?text=<encoded_receipt_text>

        WHY:
        Enables paperless POS receipts! Cashiers can click this link to instantly
        dispatch an itemized bill directly to the customer's WhatsApp.
        """
        phone = obj.customer.phone if obj.customer else ""
        # Clean phone number (strip whitespace, hyphens, and leading zero for international format)
        cleaned_phone = "".join(filter(str.isdigit, phone))
        if cleaned_phone.startswith('0'):
            cleaned_phone = '94' + cleaned_phone[1:]  # Default to Sri Lanka +94 if local 07x format

        lines = [
            f"🧾 *{obj.shop.name} - RECEIPT*",
            f"Invoice: {obj.invoice_number}",
            f"Status: {obj.get_status_display()}",
            f"Date: {obj.created_at.strftime('%Y-%m-%d %H:%M')}",
            "----------------------------",
        ]
        for item in obj.items.all():
            lines.append(f"• {item.product.name} x {item.quantity} = Rs. {item.line_total:.2f}")

        lines.extend([
            "----------------------------",
            f"*Total:* Rs. {obj.total_amount:.2f}",
            f"*Paid:* Rs. {obj.amount_paid:.2f} ({obj.get_payment_method_display()})",
        ])

        if obj.credit_amount > 0:
            lines.append(f"*Balance Due (Credit):* Rs. {obj.credit_amount:.2f}")

        lines.extend([
            "----------------------------",
            "Thank you for shopping with us! 🙏",
        ])

        full_message = "\n".join(lines)
        encoded_message = urllib.parse.quote(full_message)

        if cleaned_phone:
            return f"https://wa.me/{cleaned_phone}?text={encoded_message}"
        return f"https://wa.me/?text={encoded_message}"


class InvoiceVoidSerializer(serializers.Serializer):
    """
    Input serializer for voiding an invoice.
    """
    reason = serializers.CharField(
        required=True,
        min_length=3,
        help_text="Reason for voiding the invoice."
    )


class SalesReturnItemInputSerializer(serializers.Serializer):
    """
    Input serializer for individual line items being returned.
    """
    invoice_item_id = serializers.IntegerField(
        required=False,
        help_text="Primary key (or public_id) of the InvoiceItem."
    )
    product_id = serializers.IntegerField(
        required=False,
        help_text="Product primary key if invoice_item_id is not supplied."
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=True,
        min_value=Decimal('0.001'),
        help_text="Quantity being returned."
    )

    def validate(self, attrs):
        if not attrs.get('invoice_item_id') and not attrs.get('product_id'):
            raise serializers.ValidationError("Either 'invoice_item_id' or 'product_id' is required.")
        return attrs


class SalesReturnCreateSerializer(serializers.Serializer):
    """
    Input serializer for processing a merchandise return / credit note.
    """
    reason = serializers.CharField(
        required=True,
        min_length=3,
        help_text="Reason for return."
    )
    items = SalesReturnItemInputSerializer(
        many=True,
        allow_empty=False,
        help_text="List of items and quantities being returned."
    )


class CreditPaymentSerializer(serializers.ModelSerializer):
    """
    Handles Credit Settlements: POST /api/sales/credit-payments/
    Atomically decreases customer.total_credit_balance.
    """
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    received_by_name = serializers.CharField(source='received_by.username', read_only=True)

    class Meta:
        model = CreditPayment
        fields = (
            'id',
            'public_id',
            'customer',
            'customer_name',
            'amount_paid',
            'payment_method',
            'notes',
            'received_by',
            'received_by_name',
            'created_at',
        )
        read_only_fields = ('id', 'public_id', 'customer_name', 'received_by', 'received_by_name', 'created_at')

    def validate_customer(self, value):
        request = self.context.get('request')
        shop = getattr(getattr(request, 'user', None), 'shop', None)
        return validate_tenant_fk(value, shop, field_name="customer")

    def validate_amount_paid(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def create(self, validated_data):
        request = self.context['request']
        shop = validated_data.get('shop') or request.user.shop
        customer = validated_data['customer']
        amount_paid = validated_data['amount_paid']

        with transaction.atomic():
            # Lock customer row to prevent concurrent settlement inconsistencies
            customer_locked = Customer.objects.select_for_update().get(id=customer.id, shop=shop)
            old_balance = customer_locked.total_credit_balance

            # Deduct paid amount from credit balance
            customer_locked.total_credit_balance = max(
                Decimal('0.00'),
                customer_locked.total_credit_balance - amount_paid
            )
            customer_locked.save(update_fields=['total_credit_balance', 'updated_at'])

            payment = CreditPayment.objects.create(
                shop=shop,
                customer=customer_locked,
                amount_paid=amount_paid,
                payment_method=validated_data.get('payment_method', CreditPayment.PaymentMethod.CASH),
                notes=validated_data.get('notes', ''),
                received_by=request.user,
            )

            log_audit_event(
                action='CREDIT_PAYMENT_RECORDED',
                target_model='CreditPayment',
                target_id=str(payment.public_id),
                shop=shop,
                actor=request.user,
                before_state={
                    'customer_id': str(customer_locked.public_id),
                    'total_credit_balance': old_balance,
                },
                after_state={
                    'customer_id': str(customer_locked.public_id),
                    'amount_paid': amount_paid,
                    'total_credit_balance': customer_locked.total_credit_balance,
                }
            )

            return payment


class PDChequeSerializer(serializers.ModelSerializer):
    """
    Serializer for Post-Dated Cheques.
    """
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PDCheque
        fields = (
            'id',
            'public_id',
            'customer',
            'customer_name',
            'cheque_number',
            'bank_name',
            'amount',
            'due_date',
            'status',
            'status_display',
            'notes',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'public_id', 'customer_name', 'status_display', 'created_at', 'updated_at')

    def validate_customer(self, value):
        if value is None:
            return value
        request = self.context.get('request')
        shop = getattr(getattr(request, 'user', None), 'shop', None)
        return validate_tenant_fk(value, shop, field_name="customer")

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Cheque amount must be greater than zero.")
        return value
