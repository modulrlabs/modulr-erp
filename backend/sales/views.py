from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import log_audit_event
from core.mixins import ShopScopedViewSetMixin
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
from .permissions import IsCreditModuleEnabled, IsShopOwner
from .serializers import (
    CreditPaymentSerializer,
    CustomerSerializer,
    InvoiceCheckoutSerializer,
    InvoiceSerializer,
    InvoiceVoidSerializer,
    PDChequeSerializer,
    SalesReturnCreateSerializer,
    SalesReturnSerializer,
)


class CustomerViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing customers and their credit accounts.
    Guarded by 'enable_credit_module' and scoped to active shop tenant.
    """
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreditModuleEnabled]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Optional search by customer name or phone number
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
            )

        # Optional filter for customers with outstanding debt
        has_debt = self.request.query_params.get('has_debt', '').lower()
        if has_debt in ('true', '1'):
            queryset = queryset.filter(total_credit_balance__gt=0)

        return queryset


class InvoiceViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for POS Invoices and Sales Transactions.
    Supports atomic checkout on POST, and full itemized retrieval on GET.
    Scoped to active shop tenant via ShopScopedViewSetMixin.

    IMMUTABILITY:
    Hard deletion is forbidden (HTTP 405). Voiding and returns provide
    fiscal auditability while restoring stock and adjusting credit balances.
    """
    queryset = (
        Invoice.objects.all()
        .select_related('customer', 'cashier')
        .prefetch_related('items__product', 'returns__items__product')
    )
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        # Filter by customer
        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        # Filter by payment method
        payment_method = self.request.query_params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method.upper())

        # Search by invoice number
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search)
            )

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCheckoutSerializer
        return InvoiceSerializer

    def destroy(self, request, *args, **kwargs):
        """
        Block hard deletes of invoices to satisfy fiscal and regulatory compliance.
        """
        return Response(
            {"detail": "Invoices are legally immutable financial records and cannot be deleted. Use void or return."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def create(self, request, *args, **kwargs):
        """
        Custom create to execute atomic checkout with Idempotency-Key support,
        returning rich InvoiceSerializer response.
        """
        user = getattr(request, 'user', None)
        shop = getattr(user, 'shop', None)
        if not shop or not shop.is_active:
            raise PermissionDenied("Active shop membership required.")

        # Check client-supplied Idempotency-Key header for duplicate requests
        idempotency_key = request.headers.get('Idempotency-Key', '').strip() or None
        if idempotency_key:
            existing_invoice = Invoice.objects.filter(
                shop=shop,
                idempotency_key=idempotency_key
            ).first()
            if existing_invoice:
                response_serializer = InvoiceSerializer(existing_invoice, context={'request': request})
                return Response(response_serializer.data, status=status.HTTP_200_OK)

        checkout_serializer = InvoiceCheckoutSerializer(
            data=request.data,
            context={'request': request}
        )
        checkout_serializer.is_valid(raise_exception=True)

        try:
            invoice = checkout_serializer.save(idempotency_key=idempotency_key)
        except IntegrityError:
            # Handle concurrent race condition for duplicate idempotency key
            if idempotency_key:
                existing_invoice = Invoice.objects.filter(
                    shop=shop,
                    idempotency_key=idempotency_key
                ).first()
                if existing_invoice:
                    response_serializer = InvoiceSerializer(existing_invoice, context={'request': request})
                    return Response(response_serializer.data, status=status.HTTP_200_OK)
            raise

        response_serializer = InvoiceSerializer(invoice, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=['post'],
        url_path='void',
        permission_classes=[permissions.IsAuthenticated, IsShopOwner]
    )
    def void(self, request, public_id=None):
        """
        Void an existing invoice: POST /api/sales/invoices/{public_id}/void/
        - Permission: IsShopOwner only (Cashiers receive 403 Forbidden).
        - Restores all product stock and creates VOID_RESTORE StockMovement entries.
        - Reverses outstanding customer credit balance if applicable.
        - Excludes invoice from future dashboard aggregations.
        """
        invoice = self.get_object()
        shop = request.user.shop

        serializer = InvoiceVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']

        if invoice.status == Invoice.Status.VOIDED:
            return Response(
                {"detail": "This invoice is already voided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if invoice.returns.exists():
            return Response(
                {"detail": "Cannot void an invoice that already has processed returns. Use return instead."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Lock invoice record
            locked_invoice = Invoice.objects.select_for_update().get(id=invoice.id, shop=shop)
            if locked_invoice.status == Invoice.Status.VOIDED:
                return Response(
                    {"detail": "This invoice is already voided."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Lock products and restore stock
            items = list(locked_invoice.items.select_related('product').all())
            product_ids = [item.product_id for item in items]
            locked_products = {
                p.id: p
                for p in Product.objects.select_for_update().filter(id__in=product_ids, shop=shop)
            }

            for item in items:
                product = locked_products[item.product_id]
                product.stock_quantity += item.quantity
                product.save(update_fields=['stock_quantity', 'updated_at'])

                StockMovement.objects.create(
                    shop=shop,
                    product=product,
                    movement_type=StockMovement.MovementType.VOID_RESTORE,
                    quantity_change=item.quantity,
                    balance_after=product.stock_quantity,
                    reference_type='Invoice',
                    reference_id=str(locked_invoice.public_id),
                    notes=f"Restored from voided invoice {locked_invoice.invoice_number}: {reason}",
                    performed_by=request.user,
                )

            # Reverse customer credit if debt was incurred
            if locked_invoice.credit_amount > Decimal('0.00') and locked_invoice.customer_id:
                customer = Customer.objects.select_for_update().get(
                    id=locked_invoice.customer_id,
                    shop=shop
                )
                customer.total_credit_balance = max(
                    Decimal('0.00'),
                    customer.total_credit_balance - locked_invoice.credit_amount
                )
                customer.save(update_fields=['total_credit_balance', 'updated_at'])

            # Mark invoice voided
            locked_invoice.status = Invoice.Status.VOIDED
            locked_invoice.void_reason = reason
            locked_invoice.voided_at = timezone.now()
            locked_invoice.voided_by = request.user
            locked_invoice.save(update_fields=['status', 'void_reason', 'voided_at', 'voided_by', 'updated_at'])

            log_audit_event(
                action='INVOICE_VOIDED',
                target_model='Invoice',
                target_id=str(locked_invoice.public_id),
                shop=shop,
                actor=request.user,
                after_state={
                    'invoice_number': locked_invoice.invoice_number,
                    'reason': reason,
                    'restored_items_count': len(items),
                    'reversed_credit': locked_invoice.credit_amount,
                }
            )

        response_serializer = InvoiceSerializer(locked_invoice, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='return',
        permission_classes=[permissions.IsAuthenticated]
    )
    def return_goods(self, request, public_id=None):
        """
        Process partial or full merchandise return: POST /api/sales/invoices/{public_id}/return/
        - Validates return quantity does not exceed original purchased amount minus previous returns.
        - Restores returned stock and records SALES_RETURN in StockMovement.
        - Reverses outstanding customer credit debt up to remaining invoice credit, refunding any remainder in cash.
        - Updates invoice status to PARTIALLY_RETURNED or RETURNED.
        - Logs INVOICE_RETURNED in AuditLog.
        """
        invoice = self.get_object()
        shop = request.user.shop

        serializer = SalesReturnCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']
        items_payload = serializer.validated_data['items']

        if invoice.status == Invoice.Status.VOIDED:
            return Response(
                {"detail": "Cannot process return on a voided invoice."},
                status=status.HTTP_400_BAD_REQUEST
            )

        invoice_items_by_id = {item.id: item for item in invoice.items.all()}
        invoice_items_by_product = {item.product_id: item for item in invoice.items.all()}

        # Match input items to actual InvoiceItem records and validate returnable quantities
        resolved_returns = []
        for input_item in items_payload:
            inv_item = None
            if input_item.get('invoice_item_id'):
                inv_item = invoice_items_by_id.get(input_item['invoice_item_id'])
            elif input_item.get('product_id'):
                inv_item = invoice_items_by_product.get(input_item['product_id'])

            if not inv_item:
                raise ValidationError({"items": "One or more line items do not belong to this invoice."})

            qty_to_return = input_item['quantity']

            # Calculate already returned quantity for this line item
            already_returned = (
                SalesReturnItem.objects.filter(invoice_item=inv_item)
                .aggregate(total=Sum('quantity'))['total'] or Decimal('0.000')
            )
            available_to_return = inv_item.quantity - already_returned

            if qty_to_return > available_to_return:
                raise ValidationError(
                    f"Cannot return {qty_to_return} for '{inv_item.product.name}'. "
                    f"Maximum returnable quantity is {available_to_return}."
                )

            resolved_returns.append({
                'invoice_item': inv_item,
                'quantity': qty_to_return,
            })

        with transaction.atomic():
            locked_invoice = Invoice.objects.select_for_update().get(id=invoice.id, shop=shop)
            if locked_invoice.status == Invoice.Status.VOIDED:
                return Response(
                    {"detail": "Cannot process return on a voided invoice."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Lock products
            product_ids = [r['invoice_item'].product_id for r in resolved_returns]
            locked_products = {
                p.id: p
                for p in Product.objects.select_for_update().filter(id__in=product_ids, shop=shop)
            }

            # Calculate total refund value
            total_refund_amount = Decimal('0.00')
            for r in resolved_returns:
                inv_item = r['invoice_item']
                qty = r['quantity']
                line_total = (qty * inv_item.unit_price).quantize(Decimal('0.01'))
                r['line_total'] = line_total
                total_refund_amount += line_total

            # Generate sequential return number: RET-<YYYYMMDD>-<0001>
            today_str = timezone.now().strftime('%Y%m%d')
            daily_count = SalesReturn.objects.filter(
                shop=shop,
                created_at__date=timezone.now().date()
            ).count() + 1
            return_number = f"RET-{today_str}-{daily_count:04d}"

            # Calculate credit reversal vs cash refund
            already_reversed_credit = (
                locked_invoice.returns.aggregate(total=Sum('credit_reversed'))['total'] or Decimal('0.00')
            )
            remaining_invoice_credit = max(
                Decimal('0.00'),
                locked_invoice.credit_amount - already_reversed_credit
            )
            credit_reversed = min(total_refund_amount, remaining_invoice_credit)
            cash_refunded = total_refund_amount - credit_reversed

            # Adjust customer debt ledger if credit is reversed
            if credit_reversed > Decimal('0.00') and locked_invoice.customer_id:
                customer = Customer.objects.select_for_update().get(
                    id=locked_invoice.customer_id,
                    shop=shop
                )
                customer.total_credit_balance = max(
                    Decimal('0.00'),
                    customer.total_credit_balance - credit_reversed
                )
                customer.save(update_fields=['total_credit_balance', 'updated_at'])

            # Create SalesReturn record
            sales_return = SalesReturn.objects.create(
                shop=shop,
                return_number=return_number,
                invoice=locked_invoice,
                reason=reason,
                total_refund_amount=total_refund_amount,
                credit_reversed=credit_reversed,
                cash_refunded=cash_refunded,
                processed_by=request.user,
            )

            # Create return line items and restore inventory
            for r in resolved_returns:
                inv_item = r['invoice_item']
                qty = r['quantity']
                product = locked_products[inv_item.product_id]

                product.stock_quantity += qty
                product.save(update_fields=['stock_quantity', 'updated_at'])

                SalesReturnItem.objects.create(
                    shop=shop,
                    sales_return=sales_return,
                    invoice_item=inv_item,
                    product=product,
                    quantity=qty,
                    unit_price=inv_item.unit_price,
                    cost_price_at_sale=inv_item.cost_price_at_sale,
                    line_total=r['line_total'],
                )

                StockMovement.objects.create(
                    shop=shop,
                    product=product,
                    movement_type=StockMovement.MovementType.SALES_RETURN,
                    quantity_change=qty,
                    balance_after=product.stock_quantity,
                    reference_type='SalesReturn',
                    reference_id=str(sales_return.public_id),
                    notes=(
                        f"Restored from return {sales_return.return_number} "
                        f"on invoice {locked_invoice.invoice_number}"
                    ),
                    performed_by=request.user,
                )

            # Update Invoice status (PARTIALLY_RETURNED vs RETURNED)
            all_fully_returned = True
            for inv_item in locked_invoice.items.all():
                total_returned_for_item = (
                    SalesReturnItem.objects.filter(invoice_item=inv_item)
                    .aggregate(total=Sum('quantity'))['total'] or Decimal('0.000')
                )
                if total_returned_for_item < inv_item.quantity:
                    all_fully_returned = False
                    break

            new_status = (
                Invoice.Status.RETURNED if all_fully_returned else Invoice.Status.PARTIALLY_RETURNED
            )
            locked_invoice.status = new_status
            locked_invoice.save(update_fields=['status', 'updated_at'])

            log_audit_event(
                action='INVOICE_RETURNED',
                target_model='Invoice',
                target_id=str(locked_invoice.public_id),
                shop=shop,
                actor=request.user,
                after_state={
                    'return_number': sales_return.return_number,
                    'invoice_number': locked_invoice.invoice_number,
                    'total_refund_amount': total_refund_amount,
                    'credit_reversed': credit_reversed,
                    'cash_refunded': cash_refunded,
                    'status': locked_invoice.status,
                }
            )

        response_serializer = SalesReturnSerializer(sales_return, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CreditPaymentViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for settling customer credit accounts.
    Guarded by 'enable_credit_module' and scoped to active shop tenant.
    """
    queryset = CreditPayment.objects.all().select_related('customer', 'received_by')
    serializer_class = CreditPaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreditModuleEnabled]

    def get_queryset(self):
        queryset = super().get_queryset()

        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        return queryset


class PDChequeViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing Post-Dated Cheques.
    Guarded by 'enable_credit_module' and scoped to active shop tenant.
    """
    queryset = PDCheque.objects.all().select_related('customer')
    serializer_class = PDChequeSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreditModuleEnabled]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status (e.g. ?status=PENDING)
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        return queryset

    def perform_update(self, serializer):
        """
        Record PD_CHEQUE_UPDATED audit event when cheque status changes.
        """
        instance = self.get_object()
        old_status = instance.status
        super().perform_update(serializer)
        cheque = serializer.instance
        if old_status != cheque.status:
            log_audit_event(
                action='PD_CHEQUE_UPDATED',
                target_model='PDCheque',
                target_id=str(cheque.public_id),
                shop=cheque.shop,
                actor=self.request.user,
                before_state={'status': old_status},
                after_state={'status': cheque.status},
            )

    @action(detail=False, methods=['get'], url_path='upcoming')
    def upcoming(self, request):
        """
        Returns PENDING cheques due within the next 7 days:
        GET /api/sales/pd-cheques/upcoming/
        """
        today = timezone.now().date()
        next_week = today + timedelta(days=7)

        upcoming_cheques = self.get_queryset().filter(
            status=PDCheque.Status.PENDING,
            due_date__gte=today,
            due_date__lte=next_week
        ).order_by('due_date')

        serializer = self.get_serializer(upcoming_cheques, many=True)
        return Response({
            "start_date": str(today),
            "end_date": str(next_week),
            "count": upcoming_cheques.count(),
            "cheques": serializer.data,
        }, status=status.HTTP_200_OK)


class DashboardAnalyticsView(APIView):
    """
    Owner-only business analytics endpoint: GET /api/sales/dashboard/

    ACCURACY ADJUSTMENTS:
    - Excludes VOIDED invoices completely from all financial KPIs.
    - Subtracts returned merchandise revenue and profit from total_sales and gross_profit,
      reflecting true net profits.
    """
    permission_classes = [permissions.IsAuthenticated, IsShopOwner]

    @extend_schema(
        summary="Owner Business Dashboard Analytics",
        description=(
            "Calculates real-time financial KPIs (revenue, gross profit, cash collected, "
            "credit issued, low stock alerts, and top selling products)."
        ),
        parameters=[
            OpenApiParameter(
                name='days',
                description='Timeframe in days (e.g. 1 for today, 7 for past week, 30 for past month). Defaults to 1.',
                required=False,
                type=int,
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        shop = getattr(user, 'shop', None)
        if not shop or not shop.is_active:
            raise PermissionDenied("Active shop membership required.")

        today = timezone.now().date()

        # Parse 'days' parameter (defaults to 1 for today's metrics)
        try:
            days = int(request.query_params.get('days', '1'))
            if days <= 0:
                days = 1
        except ValueError:
            days = 1

        start_date = today - timedelta(days=days - 1)

        # Base active invoices queryset (strictly excluding VOIDED invoices)
        period_invoices = Invoice.objects.filter(
            shop=shop,
            created_at__date__gte=start_date,
            created_at__date__lte=today
        ).exclude(status=Invoice.Status.VOIDED)

        # 1. Financial Aggregations from Invoices
        invoice_aggregations = period_invoices.aggregate(
            total_sales=Sum('total_amount'),
            cash_collected=Sum('amount_paid'),
            credit_issued=Sum('credit_amount'),
            invoice_count=Count('id')
        )
        total_sales_raw = invoice_aggregations['total_sales'] or Decimal('0.00')
        cash_collected = invoice_aggregations['cash_collected'] or Decimal('0.00')
        credit_issued = invoice_aggregations['credit_issued'] or Decimal('0.00')
        invoice_count = invoice_aggregations['invoice_count'] or 0

        # 2. Merchandise Returns in this period
        period_returns = SalesReturn.objects.filter(
            shop=shop,
            created_at__date__gte=start_date,
            created_at__date__lte=today
        )
        returned_revenue = period_returns.aggregate(
            total=Sum('total_refund_amount')
        )['total'] or Decimal('0.00')

        returned_profit = SalesReturnItem.objects.filter(
            shop=shop,
            sales_return__in=period_returns
        ).aggregate(
            profit=Sum(
                (F('unit_price') - F('cost_price_at_sale')) * F('quantity'),
                output_field=models.DecimalField(max_digits=14, decimal_places=2)
            )
        )['profit'] or Decimal('0.00')

        # Net sales reflecting returned revenue
        total_sales = max(Decimal('0.00'), total_sales_raw - returned_revenue)

        # 3. Gross Profit Calculation using F() expressions across InvoiceItems minus returns
        period_items = InvoiceItem.objects.filter(
            shop=shop,
            invoice__in=period_invoices
        )
        profit_agg = period_items.aggregate(
            gross_profit=Sum(
                (F('unit_price') - F('cost_price_at_sale')) * F('quantity'),
                output_field=models.DecimalField(max_digits=14, decimal_places=2)
            )
        )
        gross_profit_raw = profit_agg['gross_profit'] or Decimal('0.00')
        gross_profit = gross_profit_raw - returned_profit

        # 4. Total Outstanding Customer Debt across the entire shop
        total_debt_agg = Customer.objects.filter(shop=shop).aggregate(
            total_debt=Sum('total_credit_balance')
        )
        total_outstanding_credit = total_debt_agg['total_debt'] or Decimal('0.00')

        # 5. Low-Stock Alert Count
        low_stock_count = Product.objects.filter(
            shop=shop,
            stock_quantity__lte=F('reorder_level')
        ).count()

        # 6. Upcoming Pending PD Cheques (due within next 7 days)
        next_7_days = today + timedelta(days=7)
        upcoming_cheques_count = PDCheque.objects.filter(
            shop=shop,
            status=PDCheque.Status.PENDING,
            due_date__gte=today,
            due_date__lte=next_7_days
        ).count()

        # 7. Top 5 Selling Products (by units sold in this time period, excluding voided)
        top_selling = (
            period_items.values('product_id', 'product__name')
            .annotate(
                units_sold=Sum('quantity'),
                revenue=Sum('line_total')
            )
            .order_by('-units_sold')[:5]
        )

        return Response({
            "period": {
                "days": days,
                "start_date": str(start_date),
                "end_date": str(today),
            },
            "kpis": {
                "total_sales": total_sales,
                "gross_profit": gross_profit,
                "cash_collected": cash_collected,
                "credit_issued": credit_issued,
                "invoice_count": invoice_count,
                "total_outstanding_credit": total_outstanding_credit,
                "low_stock_count": low_stock_count,
                "upcoming_cheques_count": upcoming_cheques_count,
            },
            "top_selling_products": list(top_selling),
        }, status=status.HTTP_200_OK)
