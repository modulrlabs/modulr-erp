from django.contrib import admin
from .models import Customer, Invoice, InvoiceItem, CreditPayment, PDCheque


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'total_credit_balance', 'shop', 'created_at')
    list_filter = ('shop',)
    search_fields = ('name', 'phone', 'shop__name')


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ('product', 'quantity', 'unit_price', 'cost_price_at_sale', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number',
        'shop',
        'customer',
        'cashier',
        'total_amount',
        'payment_method',
        'amount_paid',
        'credit_amount',
        'created_at',
    )
    list_filter = ('shop', 'payment_method', 'created_at')
    search_fields = ('invoice_number', 'customer__name', 'customer__phone', 'shop__name')
    inlines = [InvoiceItemInline]


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'amount_paid', 'payment_method', 'received_by', 'shop', 'created_at')
    list_filter = ('shop', 'payment_method')
    search_fields = ('customer__name', 'customer__phone', 'shop__name')


@admin.register(PDCheque)
class PDChequeAdmin(admin.ModelAdmin):
    list_display = (
        'cheque_number',
        'bank_name',
        'customer',
        'amount',
        'due_date',
        'status',
        'shop',
    )
    list_filter = ('shop', 'status', 'due_date')
    search_fields = ('cheque_number', 'bank_name', 'customer__name', 'shop__name')
