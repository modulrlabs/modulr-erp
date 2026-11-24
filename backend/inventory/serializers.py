from decimal import Decimal

from rest_framework import serializers

from core.mixins import validate_tenant_fk

from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for Product Categories.
    """
    product_count = serializers.IntegerField(
        source='products.count',
        read_only=True,
        help_text="Number of active products assigned to this category."
    )

    class Meta:
        model = Category
        fields = (
            'id',
            'public_id',
            'name',
            'description',
            'product_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'public_id', 'created_at', 'updated_at', 'product_count')

    def validate_name(self, value):
        """
        WHY:
        Enforce case-insensitive category name uniqueness within the same shop.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.shop:
            return value

        shop = request.user.shop
        queryset = Category.objects.filter(shop=shop, name__iexact=value.strip())

        # When updating an existing category, exclude itself from duplicate check
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)

        if queryset.exists():
            raise serializers.ValidationError("A category with this name already exists in your shop.")

        return value.strip()


class ProductSerializer(serializers.ModelSerializer):
    """
    Serializer for Products with Multi-Tenant Validation and Role-Based Field Filtering.

    KEY ARCHITECTURAL HIGHLIGHT:
    Hides 'cost_price' dynamically from Cashiers while keeping it visible to Owners.
    """
    category_name = serializers.CharField(
        source='category.name',
        read_only=True,
        default=None,
        help_text="Display name of the category for POS UI."
    )
    is_low_stock = serializers.BooleanField(
        read_only=True,
        help_text="True if stock_quantity is at or below the reorder_level."
    )

    class Meta:
        model = Product
        fields = (
            'id',
            'public_id',
            'category',
            'category_name',
            'name',
            'barcode',
            'cost_price',
            'selling_price',
            'stock_quantity',
            'reorder_level',
            'is_low_stock',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'public_id', 'is_low_stock', 'created_at', 'updated_at')

    def __init__(self, *args, **kwargs):
        """
        WHY DYNAMIC FIELD REMOVAL IN __init__:
        1. Security / Least Privilege: Cashiers only need to see retail 'selling_price'.
           Wholesale 'cost_price' and profit margins are confidential business metrics.
        2. Removing the field in __init__ prevents 'cost_price' from ever appearing
           in API output, and simultaneously prevents cashiers from injecting or altering
           cost prices via POST/PUT/PATCH payloads.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')

        # If user is not an Owner (e.g. Cashier), strip cost_price field completely
        if request and hasattr(request, 'user') and not getattr(request.user, 'is_owner', False):
            self.fields.pop('cost_price', None)

    def validate_category(self, value):
        """
        WHY CROSS-TENANT VALIDATION:
        Prevents IDOR / Foreign Key Spoofing (Rule B from ARCHITECTURE.md).
        A shop owner cannot attach a Category ID that belongs to another shop!
        """
        request = self.context.get('request')
        shop = getattr(getattr(request, 'user', None), 'shop', None)
        return validate_tenant_fk(value, shop, field_name="category")

    def validate_barcode(self, value):
        """
        WHY: Barcode must be unique within the current shop.
        """
        if not value:
            return value

        barcode = value.strip()
        request = self.context.get('request')
        if not request or not request.user or not request.user.shop:
            return barcode

        shop = request.user.shop
        queryset = Product.objects.filter(shop=shop, barcode=barcode)

        # Exclude self when updating
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)

        if queryset.exists():
            raise serializers.ValidationError(
                f"Another product with barcode '{barcode}' already exists in your shop."
            )

        return barcode

    def validate(self, attrs):
        """
        WHY: Business Logic Validations:
        - selling_price cannot be negative.
        - cost_price cannot be negative.
        - stock_quantity cannot be negative.
        - reorder_level cannot be negative.
        """
        selling_price = attrs.get('selling_price')
        if selling_price is not None and selling_price < Decimal('0.00'):
            raise serializers.ValidationError({"selling_price": "Selling price cannot be negative."})

        cost_price = attrs.get('cost_price')
        if cost_price is not None and cost_price < Decimal('0.00'):
            raise serializers.ValidationError({"cost_price": "Cost price cannot be negative."})

        stock_quantity = attrs.get('stock_quantity')
        if stock_quantity is not None and stock_quantity < Decimal('0.000'):
            raise serializers.ValidationError({"stock_quantity": "Stock quantity cannot be negative."})

        reorder_level = attrs.get('reorder_level')
        if reorder_level is not None and reorder_level < Decimal('0.000'):
            raise serializers.ValidationError({"reorder_level": "Reorder level cannot be negative."})

        return attrs


class ProductCSVUploadSerializer(serializers.Serializer):
    """
    Serializer to validate the uploaded CSV file for bulk product importing.
    """
    file = serializers.FileField(
        help_text="CSV file containing inventory products."
    )

    def validate_file(self, value):
        if not value.name.lower().endswith('.csv'):
            raise serializers.ValidationError("Only .csv files are supported.")
        # Optional: check file size (e.g., limit to 5MB)
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("CSV file size must not exceed 5MB.")
        return value
