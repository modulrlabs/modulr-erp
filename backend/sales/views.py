from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import ShopScopedViewSetMixin
from inventory.models import Product

from .models import CreditPayment, Customer, Invoice, InvoiceItem, PDCheque
from .permissions import IsCreditModuleEnabled, IsShopOwner
from .serializers import (
    CreditPaymentSerializer,
    CustomerSerializer,
    InvoiceCheckoutSerializer,
    InvoiceSerializer,
    PDChequeSerializer,
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
    """
    queryset = (
        Invoice.objects.all()
        .select_related('customer', 'cashier')
        .prefetch_related('items__product')
    )
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

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

    def create(self, request, *args, **kwargs):
        """
        Custom create to execute atomic checkout and return the rich InvoiceSerializer response.
        """
        user = getattr(request, 'user', None)
        shop = getattr(user, 'shop', None)
        if not shop or not shop.is_active:
            raise PermissionDenied("Active shop membership required.")

        checkout_serializer = InvoiceCheckoutSerializer(
            data=request.data,
            context={'request': request}
        )
        checkout_serializer.is_valid(raise_exception=True)
        invoice = checkout_serializer.save()

        # Return full invoice representation with itemized lines & WhatsApp share URL
        response_serializer = InvoiceSerializer(invoice, context={'request': request})
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

    @action(detail=False, methods=['get'], url_path='upcoming')
    def upcoming(self, request):
        """
        Returns PENDING cheques due within the next 7 days:
        GET /api/sales/pd-cheques/upcoming/

        WHY:
        Helps store owners plan cash flow by anticipating bank deposits for the upcoming week.
        Scoped strictly through self.get_queryset() to prevent cross-tenant leakage.
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

    WHY:
    Provides shop owners with real-time financial KPIs (revenue, profit, cash, credit,
    inventory alerts, and top products) calculated directly within PostgreSQL via Django ORM.
    Cashiers and users without an active shop subscription are strictly forbidden (403).
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

        # Base invoices queryset for this tenant and time period
        period_invoices = Invoice.objects.filter(
            shop=shop,
            created_at__date__gte=start_date,
            created_at__date__lte=today
        )

        # 1. Financial Aggregations from Invoices
        invoice_aggregations = period_invoices.aggregate(
            total_sales=Sum('total_amount'),
            cash_collected=Sum('amount_paid'),
            credit_issued=Sum('credit_amount'),
            invoice_count=Count('id')
        )
        total_sales = invoice_aggregations['total_sales'] or Decimal('0.00')
        cash_collected = invoice_aggregations['cash_collected'] or Decimal('0.00')
        credit_issued = invoice_aggregations['credit_issued'] or Decimal('0.00')
        invoice_count = invoice_aggregations['invoice_count'] or 0

        # 2. Gross Profit Calculation using F() expressions across InvoiceItems
        # WHY F(): Computes profit directly inside PostgreSQL SQL engine in a single query.
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
        gross_profit = profit_agg['gross_profit'] or Decimal('0.00')

        # 3. Total Outstanding Customer Debt across the entire shop
        total_debt_agg = Customer.objects.filter(shop=shop).aggregate(
            total_debt=Sum('total_credit_balance')
        )
        total_outstanding_credit = total_debt_agg['total_debt'] or Decimal('0.00')

        # 4. Low-Stock Alert Count
        low_stock_count = Product.objects.filter(
            shop=shop,
            stock_quantity__lte=F('reorder_level')
        ).count()

        # 5. Upcoming Pending PD Cheques (due within next 7 days)
        next_7_days = today + timedelta(days=7)
        upcoming_cheques_count = PDCheque.objects.filter(
            shop=shop,
            status=PDCheque.Status.PENDING,
            due_date__gte=today,
            due_date__lte=next_7_days
        ).count()

        # 6. Top 5 Selling Products (by units sold in this time period)
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
