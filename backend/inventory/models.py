from decimal import Decimal

from django.db import models

from core.models import ShopAwareModel, User


class Category(ShopAwareModel):
    """
    Categorizes products for a shop (e.g., 'Groceries', 'Beverages', 'Electronics').

    WHY ShopAwareModel:
    Every shop organizes their inventory differently. By inheriting from ShopAwareModel,
    categories are isolated to the tenant. Two different shops can each have a category
    named 'Beverages' without name collision in the database.
    """
    name = models.CharField(
        max_length=150,
        help_text="Category name (e.g. Dairy, Beverages, Snacks)."
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the category."
    )

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']
        # WHY unique_together:
        # A shop cannot have two categories with the exact same name,
        # but Shop A and Shop B can both have their own "Dairy" category.
        unique_together = ('shop', 'name')

    def __str__(self):
        return f"{self.name} ({self.shop.name})"


class Product(ShopAwareModel):
    """
    Represents an inventory item sold at the POS.

    WHY ShopAwareModel:
    Ensures complete data isolation between tenants. Product prices, barcodes,
    and stock counts are strictly bound to the authenticated user's shop.
    """
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        help_text="Product category. If a category is deleted, product remains uncategorized (SET_NULL)."
    )
    name = models.CharField(
        max_length=255,
        help_text="Product name (e.g., 'Anchor Full Cream Milk 400g')."
    )
    # null=True is necessary for unique_together ('shop', 'barcode') so multiple barcode-less items don't collide
    barcode = models.CharField(  # noqa: DJ001
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Barcode / EAN / UPC for fast POS scanning. Indexed for millisecond lookups.",
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Purchase cost from supplier. Sensitive business information: hidden from Cashiers."
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Retail selling price charged to customers at POS checkout."
    )
    stock_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text="Current available inventory quantity in store (supports fractional units like kg/liters)."
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('5.000'),
        help_text="Minimum stock threshold. When stock_quantity <= reorder_level, low-stock alert triggers."
    )

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
        # WHY unique_together:
        # Shop A and Shop B might both sell "Coca Cola 500ml" with the identical universal barcode 5449000000996.
        # A global unique constraint on barcode would prevent Shop B from adding it!
        # Scoping uniqueness to ('shop', 'barcode') guarantees multi-tenant coexistence.
        unique_together = ('shop', 'barcode')

    @property
    def is_low_stock(self) -> bool:
        """
        WHY: Handy helper for POS dashboards to visually highlight items needing reorder.
        """
        return self.stock_quantity <= self.reorder_level

    def __str__(self):
        return f"{self.name} ({self.barcode or 'No Barcode'}) - Stock: {self.stock_quantity}"


class StockMovementQuerySet(models.QuerySet):
    """
    QuerySet that blocks bulk updates and bulk deletes to preserve immutable stock history.
    """
    def update(self, **kwargs):
        raise RuntimeError("StockMovement ledger entries are immutable and cannot be updated.")

    def delete(self):
        raise RuntimeError("StockMovement ledger entries are immutable and cannot be deleted.")


class StockMovementManager(models.Manager.from_queryset(StockMovementQuerySet)):
    """
    Manager enforcing immutable stock movements on all queries.
    """
    pass


class StockMovement(ShopAwareModel):
    """
    Append-only, immutable inventory ledger recording every stock fluctuation.

    WHY IMMUTABLE STOCK LEDGER:
    Directly mutating product.stock_quantity without an audit trail leads to untraceable
    shrinkage, theft, and discrepancy. Every single stock change (sale, void, return, restock,
    damage, or CSV import) MUST record an immutable StockMovement entry with balance_after.
    """
    class MovementType(models.TextChoices):
        SALE = 'SALE', 'Sale'
        VOID_RESTORE = 'VOID_RESTORE', 'Void Restoration'
        SALES_RETURN = 'SALES_RETURN', 'Sales Return'
        CSV_IMPORT = 'CSV_IMPORT', 'CSV Import'
        INITIAL_STOCK = 'INITIAL_STOCK', 'Initial Stock'
        ADJUSTMENT = 'ADJUSTMENT', 'Stock Adjustment'

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        help_text="The product whose stock level changed."
    )
    movement_type = models.CharField(
        max_length=30,
        choices=MovementType.choices,
        db_index=True,
        help_text="Category of stock transaction."
    )
    quantity_change = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text="Delta quantity (+ for stock added/restored, - for stock sold/deducted)."
    )
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text="Product stock_quantity immediately following this movement."
    )
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Model name associated with this transaction (e.g., 'Invoice', 'SalesReturn')."
    )
    reference_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Public UUID string or ID of the originating document."
    )
    notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable context or explanation for this stock change."
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        help_text="Staff member who executed or authorized this inventory action."
    )

    objects = StockMovementManager()

    class Meta:
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shop', 'product', 'created_at']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def __str__(self):
        sign = "+" if self.quantity_change > 0 else ""
        return (
            f"[{self.get_movement_type_display()}] {self.product.name}: "
            f"{sign}{self.quantity_change} -> Balance: {self.balance_after}"
        )

    def save(self, *args, **kwargs):
        """
        Prevent updating existing stock ledger rows.
        """
        if self.pk is not None:
            raise RuntimeError("StockMovement ledger entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Prevent deleting stock ledger rows.
        """
        raise RuntimeError("StockMovement ledger entries are immutable and cannot be deleted.")
