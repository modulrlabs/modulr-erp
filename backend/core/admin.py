from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditLog, Shop, User


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only Django Admin configuration for immutable AuditLog entries.
    """
    list_display = (
        'created_at',
        'shop',
        'actor_username',
        'action',
        'target_model',
        'target_id',
        'ip_address',
    )
    list_filter = ('action', 'target_model', 'shop', 'created_at')
    search_fields = ('actor_username', 'target_id', 'action')
    ordering = ('-created_at',)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
