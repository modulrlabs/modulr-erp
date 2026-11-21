import urllib.parse
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Customer, Invoice, InvoiceItem, CreditPayment, PDCheque
from inventory.models import Product


class CustomerSerializer(serializers.ModelSerializer):
    """
    Serializer for Customer details and Credit Ledger balance.
    """
    class Meta:
        model = Customer
        fields = (
            'id',
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
        read_only_fields = ('id', 'total_credit_balance', 'created_at', 'updated_at')


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
        if request and hasattr(request, 'user') and not getattr(request.user, 'is_owner', False):
            self.fields.pop('cost_price_at_sale', None)


class InvoiceItemInputSerializer(serializers.Serializer):
    """
    Input serializer for each item being rung up at checkout.
    """
    product_id = serializers.IntegerField(required=True)
    quantity = serializers.IntegerField(required=True, min_value=1)


class InvoiceCheckoutSerializer(serializers.Serializer):
    """
    Handles Atomic POS Checkout: POST /api/sales/invoices/

    WHY:
    A POS sale involves 4 distinct, interdependent database actions:
    1. Stock check & deduction with select_for_update() row locks.
    2. Generating the invoice header with auto-sequenced numbering.
    3. Creating line items with cost-price snapshots.
    4. Updating customer debt ledger if payment is credit / pay-later.
    All 4 MUST execute inside transaction.atomic() to guarantee financial integrity.
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
        if value is None:
            return value

        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            if value.shop != request.user.shop:
                raise serializers.ValidationError("Customer does not belong to your shop.")
        return value

    def create(self, validated_data):
        request = self.context['request']
        shop = request.user.shop
        cashier = request.user

        customer = validated_data.get('customer')
        payment_method = validated_data.get('payment_method')
        discount = validated_data.get('discount', Decimal('0.00'))
        amount_paid = validated_data.get('amount_paid', Decimal('0.00'))
        notes = validated_data.get('notes', '')
        items_data = validated_data.get('items', [])

        product_ids = [item['product_id'] for item in items_data]
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
                .filter(id__in=product_ids, shop=shop)
            )

            # Validate that all requested products were found in this tenant
            if len(products) != len(product_ids):
                found_ids = {p.id for p in products}
                missing_ids = set(product_ids) - found_ids
                raise serializers.ValidationError(
                    f"Products with IDs {list(missing_ids)} do not exist in your shop."
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

                line_total = product.selling_price * quantity
                subtotal += line_total

                line_items_to_create.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price': product.selling_price,
                    # WHY snapshot: Cost prices change over time; snapshotting freezes historical profit.
                    'cost_price_at_sale': product.cost_price,
                    'line_total': line_total,
                })

            # Calculate Net Payable Total
            total_amount = max(Decimal('0.00'), subtotal - discount)

            # If amount_paid wasn't specified for CASH/CARD, assume fully paid
            if payment_method in (Invoice.PaymentMethod.CASH, Invoice.PaymentMethod.CARD) and amount_paid == Decimal('0.00'):
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
                total_amount=total_amount,
                payment_method=payment_method,
                amount_paid=amount_paid,
                credit_amount=credit_amount,
                notes=notes,
            )

            # Create Invoice Line Items
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

            return invoice


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Detailed read serializer for Invoices, including line items and WhatsApp receipt share link.
    """
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default="Walk-in Customer")
    customer_phone = serializers.CharField(source='customer.phone', read_only=True, default="")
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    whatsapp_share_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            'id',
            'invoice_number',
            'customer',
            'customer_name',
            'customer_phone',
            'cashier',
            'cashier_name',
            'subtotal',
            'discount',
            'total_amount',
            'payment_method',
            'amount_paid',
            'credit_amount',
            'notes',
            'items',
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
            'customer',
            'customer_name',
            'amount_paid',
            'payment_method',
            'notes',
            'received_by',
            'received_by_name',
            'created_at',
        )
        read_only_fields = ('id', 'customer_name', 'received_by', 'received_by_name', 'created_at')

    def validate_customer(self, value):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            if value.shop != request.user.shop:
                raise serializers.ValidationError("Customer does not belong to your shop.")
        return value

    def validate_amount_paid(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def create(self, validated_data):
        request = self.context['request']
        shop = request.user.shop
        customer = validated_data['customer']
        amount_paid = validated_data['amount_paid']

        with transaction.atomic():
            # Lock customer row to prevent concurrent settlement inconsistencies
            customer_locked = Customer.objects.select_for_update().get(id=customer.id, shop=shop)

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
        read_only_fields = ('id', 'customer_name', 'status_display', 'created_at', 'updated_at')

    def validate_customer(self, value):
        if value is None:
            return value
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            if value.shop != request.user.shop:
                raise serializers.ValidationError("Customer does not belong to your shop.")
        return value

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Cheque amount must be greater than zero.")
        return value
