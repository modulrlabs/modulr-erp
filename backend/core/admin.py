from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Shop, User


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Shop (Tenant) model.
    """
    list_display = (
        'name',
        'phone',
        'is_active',
        'enable_credit_module',
        'enable_whatsapp_alerts',
        'created_at',
    )
    list_filter = (
        'is_active',
        'enable_credit_module',
        'enable_whatsapp_alerts',
    )
    search_fields = ('name', 'phone')
    ordering = ('-created_at',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom UserAdmin displaying the tenant 'shop' and 'role' fields in Django Admin.
    """
    list_display = (
        'username',
        'email',
        'shop',
        'role',
        'is_staff',
        'is_active',
    )
    list_filter = ('role', 'is_staff', 'is_active', 'shop')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Shop & SaaS Role', {'fields': ('shop', 'role')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Shop & SaaS Role', {'fields': ('shop', 'role')}),
    )
