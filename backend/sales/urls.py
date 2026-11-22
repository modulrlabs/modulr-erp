from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CreditPaymentViewSet,
    CustomerViewSet,
    DashboardAnalyticsView,
    InvoiceViewSet,
    PDChequeViewSet,
)

router = DefaultRouter()
router.register('customers', CustomerViewSet, basename='customer')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('credit-payments', CreditPaymentViewSet, basename='credit-payment')
router.register('pd-cheques', PDChequeViewSet, basename='pd-cheque')

urlpatterns = [
    path('dashboard/', DashboardAnalyticsView.as_view(), name='dashboard'),
    path('', include(router.urls)),
]
