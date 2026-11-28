from django.contrib import admin

from .models import (
    CreditPayment,
    Customer,
    Invoice,
    InvoiceItem,
    PDCheque,
    SalesReturn,
    SalesReturnItem,
)


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
        'status',
        'shop',
        'customer',
        'cashier',
        'total_amount',
        'payment_method',
        'amount_paid',
        'credit_amount',
        'created_at',
    )
    list_filter = ('shop', 'status', 'payment_method', 'created_at')
    search_fields = ('invoice_number', 'customer__name', 'customer__phone', 'shop__name')
    readonly_fields = ('invoice_number', 'idempotency_key', 'created_at', 'updated_at')
    inlines = [InvoiceItemInline]

    def has_delete_permission(self, request, obj=None):
        return False


class SalesReturnItemInline(admin.TabularInline):
    model = SalesReturnItem
    extra = 0
    fields = ('product', 'invoice_item', 'quantity', 'unit_price', 'cost_price_at_sale', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(SalesReturn)
class SalesReturnAdmin(admin.ModelAdmin):
    list_display = (
        'return_number',
        'invoice',
        'shop',
        'total_refund_amount',
        'credit_reversed',
        'cash_refunded',
        'processed_by',
        'created_at',
    )
    list_filter = ('shop', 'created_at')
    search_fields = ('return_number', 'invoice__invoice_number', 'shop__name')
    readonly_fields = [f.name for f in SalesReturn._meta.fields]
    inlines = [SalesReturnItemInline]

    def has_delete_permission(self, request, obj=None):
        return False


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
