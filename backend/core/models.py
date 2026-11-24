import uuid

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
        CASHIER = 'CASHIER', 'Cashier'

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
        max_length=10,
        choices=Role.choices,
        default=Role.CASHIER,
        help_text=(
            "Defines the user's operational privileges "
            "(Owner has full store control; Cashier is restricted to POS checkout)."
        ),
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
