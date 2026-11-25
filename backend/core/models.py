import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class Shop(models.Model):
    """
    Tenant model representing an individual shop or business entity.

    WHY:
    In a row-level multi-tenant SaaS architecture, the Shop is the root boundary
    of data isolation. Every transaction, product, customer, and staff member
    belongs to a specific Shop.
    """
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Public-facing immutable UUID for API exposure and secure references."
    )
    name = models.CharField(
        max_length=255,
        help_text="The trading name or business name of the shop."
    )
    address = models.TextField(
        blank=True,
        help_text="Physical location of the shop (displayed on printed POS receipts)."
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact number for customer queries and official communication."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this shop subscription is active. Inactive shops cannot access the POS."
    )

    # --------------------------------------------------------------------------
    # Modular Feature Flags
    # WHY:
    # Instead of maintaining separate codebases or custom deployments for different
    # clients, boolean flags on the Shop model let us toggle ERP modules on/off dynamically.
    # --------------------------------------------------------------------------
    enable_credit_module = models.BooleanField(
        default=False,
        help_text="Feature flag: Enables customer credit accounts, ledger balances, and pay-later terms."
    )
    enable_whatsapp_alerts = models.BooleanField(
        default=False,
        help_text="Feature flag: Enables automated WhatsApp PDF receipts and notification alerts."
    )

    # Audit timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the shop was registered."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when shop details were last modified."
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Shop'
        verbose_name_plural = 'Shops'

    def __str__(self):
        return self.name


class ShopSettings(models.Model):
    """
    Per-shop RBAC delegation toggles and operational guardrails.

    WHY SEPARATE FROM Shop:
    Keeps Shop focused on tenant identity and SaaS subscription flags while
    allowing Owners to configure granular delegation rules for Managers and
    discount caps for Cashiers.
    """
    shop = models.OneToOneField(
        Shop,
        on_delete=models.CASCADE,
        related_name='settings',
        help_text="The tenant shop these RBAC and operational settings apply to."
    )
    managers_can_edit_products = models.BooleanField(
        default=False,
        help_text="Grants inventory.manage_products to MANAGER users."
    )
    managers_can_view_cost_price = models.BooleanField(
        default=False,
        help_text="Grants inventory.view_cost_price to MANAGER users."
    )
    managers_can_view_profit = models.BooleanField(
        default=False,
        help_text="Grants dashboard.view_profit to MANAGER users."
    )
    managers_can_manage_purchasing = models.BooleanField(
        default=False,
        help_text="Grants purchasing.manage to MANAGER users (Phase 2)."
    )
    managers_can_manage_cashiers = models.BooleanField(
        default=False,
        help_text="Grants staff.manage_cashiers_only to MANAGER users."
    )
    cashier_max_discount_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Maximum invoice discount percentage a CASHIER may apply (0.00-100.00)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Shop Settings'
        verbose_name_plural = 'Shop Settings'

    def __str__(self):
        return f"Settings for {self.shop.name}"


class User(AbstractUser):
    """
    Custom user model representing shop staff (Owners, Cashiers) and platform admins.

    WHY:
    Extending AbstractUser gives us full control over user fields (adding 'shop' and 'role')
    from the very beginning of the project, while retaining all built-in Django auth mechanisms
    (secure password hashing, password reset tokens, permissions, and session management).
    """

    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        MANAGER = 'MANAGER', 'Manager'
        CASHIER = 'CASHIER', 'Cashier'
        INVENTORY_MANAGER = 'INVENTORY_MANAGER', 'Inventory Manager'
        ACCOUNTANT = 'ACCOUNTANT', 'Accountant'

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Public-facing immutable UUID for API exposure and secure references."
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        help_text=(
            "The shop/tenant this user works for. "
            "Can be null only for platform superusers/administrators who manage the entire SaaS."
        )
    )
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.CASHIER,
        help_text=(
            "Defines the user's operational privileges "
            "(Owner has full store control; other roles are governed by RBAC v2)."
        ),
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="Forces user to change password on next login (e.g., after owner reset or invite)."
    )

    @property
    def is_owner(self) -> bool:
        """
        WHY: Reusable helper property for quick role checks in views, serializers, and permissions.
        """
        return self.role == self.Role.OWNER

    @property
    def is_cashier(self) -> bool:
        """
        WHY: Reusable helper property for cashier-specific UI limits and operational restrictions.
        """
        return self.role == self.Role.CASHIER

    def __str__(self):
        shop_name = self.shop.name if self.shop else "Platform Admin"
        return f"{self.username} ({self.get_role_display()}) - {shop_name}"


class ShopAwareModel(models.Model):
    """
    Abstract base model that enforces row-level multi-tenancy across all business models.

    WHY:
    Any future business entity (e.g., Product, Sale, Customer, Category) in other apps
    (like 'inventory' or 'sales') must inherit from this base class.
    This guarantees that every record in the database is automatically stamped with a
    'shop' foreign key and timestamp fields, adhering to our DRY architecture.
    """
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Public-facing immutable UUID for API exposure and secure references."
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
        help_text="The tenant/shop that owns this record."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the record was created for audit trails."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last modified."
    )

    class Meta:
        abstract = True


class AuditLogQuerySet(models.QuerySet):
    """
    QuerySet that blocks bulk update and delete operations on AuditLog.
    """
    def update(self, *args, **kwargs):
        raise ValueError("AuditLog entries are immutable and cannot be modified.")

    def delete(self):
        raise ValueError("AuditLog entries are immutable and cannot be deleted.")


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    """
    Manager for immutable AuditLog entries.
    """
    pass


class AuditLog(models.Model):
    """
    Immutable audit log capturing critical security, financial, and inventory actions.

    WHY:
    In a SaaS ERP handling money, inventory adjustments, and multi-tenant user access,
    an immutable audit trail is an essential regulatory and operational requirement.
    It guarantees that every action (logins, price changes, discounts, credit payments)
    can be attributed to an actor, IP, timestamp, and state before/after.

    CRITICAL IMMUTABILITY ENFORCEMENT:
    - Overridden save() raises ValueError if self.pk is not None (cannot be edited).
    - Overridden delete() raises ValueError (cannot be deleted).
    - Custom QuerySet/Manager raises ValueError on bulk .update() and .delete().
    """
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        editable=False,
        help_text="Public-facing immutable UUID for API exposure and secure references."
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_index=True,
        help_text="The tenant shop where this event occurred (null for platform/pre-auth events)."
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="User who initiated this action (null if anonymous/system/unauthenticated)."
    )
    actor_username = models.CharField(
        max_length=150,
        blank=True,
        help_text="Snapshot of the username at action time (preserved even if User is deleted)."
    )
    action = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Machine-readable action identifier (e.g., LOGIN_SUCCESS, PRODUCT_PRICE_CHANGED)."
    )
    target_model = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Name of the model affected (e.g., Product, Invoice, User)."
    )
    target_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Identifier (public_id or ID) of the target entity affected."
    )
    before_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="State snapshot before the action was performed."
    )
    after_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="State snapshot after the action was performed."
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address that initiated the request."
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        help_text="Client HTTP User-Agent string."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the audit log was recorded."
    )

    objects = AuditLogManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shop', '-created_at']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        shop_name = self.shop.name if self.shop else "System/Auth"
        ts = self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        actor = self.actor_username or 'System'
        return f"[{ts}] {shop_name} - {self.action} by {actor}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AuditLog entries are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog entries are immutable and cannot be deleted.")

