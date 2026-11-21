from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Customer, Invoice, CreditPayment, PDCheque
from .serializers import (
    CustomerSerializer,
    InvoiceSerializer,
    InvoiceCheckoutSerializer,
    CreditPaymentSerializer,
    PDChequeSerializer,
)
from .permissions import IsCreditModuleEnabled


class CustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customers and their credit accounts.
    Guarded by the 'enable_credit_module' feature flag.
    """
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreditModuleEnabled]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated or not user.shop:
            return Customer.objects.none()

        queryset = Customer.objects.filter(shop=user.shop)

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

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.shop)


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for POS Invoices and Sales Transactions.
    Supports atomic checkout on POST, and full itemized retrieval on GET.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated or not user.shop:
            return Invoice.objects.none()

        queryset = (
            Invoice.objects.filter(shop=user.shop)
            .select_related('customer', 'cashier')
            .prefetch_related('items__product')
        )

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
        checkout_serializer = InvoiceCheckoutSerializer(
            data=request.data,
            context={'request': request}
        )
        checkout_serializer.is_valid(raise_exception=True)
        invoice = checkout_serializer.save()

        # Return full invoice representation with itemized lines & WhatsApp share URL
        response_serializer = InvoiceSerializer(invoice, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CreditPaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for settling customer credit accounts.
    Guarded by 'enable_credit_module'.
    """
    serializer_class = CreditPaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreditModuleEnabled]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated or not user.shop:
            return CreditPayment.objects.none()

        queryset = CreditPayment.objects.filter(shop=user.shop).select_related('customer', 'received_by')

        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        return queryset

    def perform_create(self, serializer):
        serializer.save()


class PDChequeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Post-Dated Cheques.
    Guarded by 'enable_credit_module'.
    """
    serializer_class = PDChequeSerializer
    permission_classes = [permissions.IsAuthenticated, IsCreditModuleEnabled]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated or not user.shop:
            return PDCheque.objects.none()

        queryset = PDCheque.objects.filter(shop=user.shop).select_related('customer')

        # Filter by status (e.g. ?status=PENDING)
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        return queryset

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.shop)

    @action(detail=False, methods=['get'], url_path='upcoming')
    def upcoming(self, request):
        """
        Returns PENDING cheques due within the next 7 days:
        GET /api/sales/pd-cheques/upcoming/

        WHY:
        Helps store owners plan cash flow by anticipating bank deposits for the upcoming week.
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
