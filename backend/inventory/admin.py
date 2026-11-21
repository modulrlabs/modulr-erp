from django.contrib import admin
from .models import Category, Product


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
