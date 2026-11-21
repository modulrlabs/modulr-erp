from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, InvoiceViewSet, CreditPaymentViewSet, PDChequeViewSet

router = DefaultRouter()
router.register('customers', CustomerViewSet, basename='customer')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('credit-payments', CreditPaymentViewSet, basename='credit-payment')
router.register('pd-cheques', PDChequeViewSet, basename='pd-cheque')

urlpatterns = [
    path('', include(router.urls)),
]
