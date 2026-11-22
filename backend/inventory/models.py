from django.db import models

from core.models import ShopAwareModel


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
    stock_quantity = models.IntegerField(
        default=0,
        help_text="Current available inventory quantity in store."
    )
    reorder_level = models.IntegerField(
        default=5,
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
