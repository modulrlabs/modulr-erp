import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from core.audit import log_audit_event
from core.mixins import ShopScopedViewSetMixin

from .models import Category, Product
from .permissions import IsShopOwner, IsShopOwnerOrReadOnly
from .serializers import (
    CategorySerializer,
    ProductCSVUploadSerializer,
    ProductSerializer,
)


class CategoryViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing product categories.
    - Read (GET): Allowed for both Cashiers and Owners.
    - Write (POST, PUT, PATCH, DELETE): Restricted to Owners.
    - Tenant Isolation: Scoped to request.user.shop via ShopScopedViewSetMixin.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsShopOwnerOrReadOnly]


class ProductViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing products, barcode lookups, and bulk CSV imports.
    - Read (GET): Allowed for both Cashiers and Owners.
    - Write (POST, PUT, PATCH, DELETE): Restricted to Owners.
    - Tenant Isolation: Scoped to request.user.shop via ShopScopedViewSetMixin.
    """
    queryset = Product.objects.all().select_related('category')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsShopOwnerOrReadOnly]

    def get_queryset(self):
        """
        WHY: Systematic tenant scoping via super().get_queryset() combined with
        POS search and filtering query parameters.
        """
        queryset = super().get_queryset()

        # 1. Text Search (searches name OR barcode)
        search_query = self.request.query_params.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(barcode__icontains=search_query)
            )

        # 2. Filter by Category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # 3. Filter Low Stock Items (useful for inventory management)
        low_stock = self.request.query_params.get('low_stock', '').lower()
        if low_stock in ('true', '1'):
            queryset = queryset.filter(stock_quantity__lte=F('reorder_level'))

        return queryset

    def perform_create(self, serializer):
        """
        Record PRODUCT_CREATED audit event upon creation.
        """
        super().perform_create(serializer)
        product = serializer.instance
        log_audit_event(
            action='PRODUCT_CREATED',
            target_model='Product',
            target_id=str(product.public_id),
            shop=product.shop,
            actor=self.request.user,
            after_state={
                'name': product.name,
                'barcode': product.barcode,
                'cost_price': product.cost_price,
                'selling_price': product.selling_price,
                'stock_quantity': product.stock_quantity,
            }
        )

    def perform_update(self, serializer):
        """
        Record PRODUCT_PRICE_CHANGED and PRODUCT_STOCK_CHANGED audit events.
        """
        instance = self.get_object()
        old_cost = instance.cost_price
        old_selling = instance.selling_price
        old_stock = instance.stock_quantity

        super().perform_update(serializer)
        product = serializer.instance

        if old_cost != product.cost_price or old_selling != product.selling_price:
            log_audit_event(
                action='PRODUCT_PRICE_CHANGED',
                target_model='Product',
                target_id=str(product.public_id),
                shop=product.shop,
                actor=self.request.user,
                before_state={'cost_price': old_cost, 'selling_price': old_selling},
                after_state={'cost_price': product.cost_price, 'selling_price': product.selling_price},
            )

        if old_stock != product.stock_quantity:
            log_audit_event(
                action='PRODUCT_STOCK_CHANGED',
                target_model='Product',
                target_id=str(product.public_id),
                shop=product.shop,
                actor=self.request.user,
                before_state={'stock_quantity': old_stock},
                after_state={'stock_quantity': product.stock_quantity},
            )

    @action(detail=False, methods=['get'], url_path='by-barcode')
    def by_barcode(self, request):
        """
        Fast lookup endpoint for POS barcode scanners:
        GET /api/inventory/products/by-barcode/?code=5449000000996

        WHY:
        When a cashier scans an item with a handheld barcode scanner, the POS UI
        needs an instantaneous response without paginating through a general list.
        Scoped strictly through self.get_queryset() to prevent cross-tenant leakage.
        """
        barcode = request.query_params.get('code', '').strip()

        if not barcode:
            return Response(
                {"detail": "Barcode query parameter 'code' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        product = self.get_queryset().filter(barcode=barcode).first()

        if not product:
            return Response(
                {"detail": f"Product with barcode '{barcode}' was not found in your inventory."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=['post'],
        url_path='upload-csv',
        permission_classes=[permissions.IsAuthenticated, IsShopOwner],
        parser_classes=[MultiPartParser, FormParser]
    )
    def upload_csv(self, request):
        """
        Bulk CSV inventory import endpoint:
        POST /api/inventory/products/upload-csv/

        Expected CSV columns:
        name, barcode, category, cost_price, selling_price, stock_quantity, reorder_level

        WHY transaction.atomic():
        Bulk imports must be reliable and transactional. If a catastrophic format
        error occurs halfway through, we can report clean feedback without leaving
        partially imported inventory in an inconsistent state.
        """
        shop = getattr(request.user, 'shop', None)
        if not shop or not shop.is_active:
            raise PermissionDenied("Active shop membership required.")

        upload_serializer = ProductCSVUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        csv_file = upload_serializer.validated_data['file']

        try:
            # Decode CSV content into text
            decoded_file = csv_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(decoded_file))
        except Exception as e:
            return Response(
                {"detail": f"Failed to parse CSV file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Normalize column header names to lowercase
        if not reader.fieldnames:
            return Response(
                {"detail": "Uploaded CSV file is empty."},
                status=status.HTTP_400_BAD_REQUEST
            )

        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for row_idx, row in enumerate(reader, start=2):  # start=2 considering header is row 1
                row_cleaned = {k.strip().lower(): v.strip() for k, v in row.items() if k}

                name = row_cleaned.get('name')
                if not name:
                    errors.append(f"Row {row_idx}: 'name' is required.")
                    continue

                barcode = row_cleaned.get('barcode') or None
                category_name = row_cleaned.get('category')

                # Parse prices and stock
                try:
                    selling_price = Decimal(row_cleaned.get('selling_price', '0.00'))
                    cost_price = Decimal(row_cleaned.get('cost_price', '0.00'))
                    stock_quantity = int(row_cleaned.get('stock_quantity', '0'))
                    reorder_level = int(row_cleaned.get('reorder_level', '5'))
                except (InvalidOperation, ValueError):
                    errors.append(f"Row {row_idx} ({name}): Invalid numerical format in price or quantity.")
                    continue

                # Resolve or auto-create category within this shop
                category_instance = None
                if category_name:
                    category_instance, _ = Category.objects.get_or_create(
                        shop=shop,
                        name=category_name
                    )

                # Upsert Product: If barcode matches existing product in this shop, update it
                product = None
                if barcode:
                    product = Product.objects.filter(shop=shop, barcode=barcode).first()

                if product:
                    # Update existing product
                    product.name = name
                    product.category = category_instance
                    product.cost_price = cost_price
                    product.selling_price = selling_price
                    product.stock_quantity = stock_quantity
                    product.reorder_level = reorder_level
                    product.save()
                    updated_count += 1
                else:
                    # Create new product
                    Product.objects.create(
                        shop=shop,
                        category=category_instance,
                        name=name,
                        barcode=barcode,
                        cost_price=cost_price,
                        selling_price=selling_price,
                        stock_quantity=stock_quantity,
                        reorder_level=reorder_level,
                    )
                    created_count += 1

        log_audit_event(
            action='CSV_IMPORT',
            target_model='Product',
            shop=shop,
            actor=request.user,
            after_state={
                'created_count': created_count,
                'updated_count': updated_count,
                'error_count': len(errors),
            }
        )

        return Response({
            "message": "CSV inventory processing completed.",
            "created": created_count,
            "updated": updated_count,
            "errors": errors,
        }, status=status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS)
