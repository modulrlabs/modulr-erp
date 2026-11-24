from django.contrib import admin

from .models import Category, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'created_at')
    list_filter = ('shop',)
    search_fields = ('name', 'shop__name')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'shop',
        'barcode',
        'category',
        'selling_price',
        'cost_price',
        'stock_quantity',
        'reorder_level',
        'is_low_stock',
    )
    list_filter = ('shop', 'category')
    search_fields = ('name', 'barcode', 'shop__name')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'public_id',
        'shop',
        'product',
        'movement_type',
        'quantity_change',
        'balance_after',
        'reference_type',
        'reference_id',
        'performed_by',
        'created_at',
    )
    list_filter = ('shop', 'movement_type', 'reference_type')
    search_fields = ('product__name', 'reference_id', 'notes')
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
