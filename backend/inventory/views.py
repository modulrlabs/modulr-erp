import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from core.audit import log_audit_event
from core.mixins import ShopScopedViewSetMixin, SoftDeleteViewSetMixin
from core.permissions import HasPermission

from .filters import ProductFilter
from .models import Category, Product, StockMovement
from .serializers import (
    CategorySerializer,
    ProductCSVUploadSerializer,
    ProductSerializer,
)


class CategoryViewSet(SoftDeleteViewSetMixin, ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing product categories.
    - Read (GET): Requires `inventory.view_products`.
    - Write / Soft Delete / Restore: Requires `inventory.manage_products`.
    - Tenant Isolation: Scoped to request.user.shop via ShopScopedViewSetMixin.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated, HasPermission]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    action_permissions = {
        'list': 'inventory.view_products',
        'retrieve': 'inventory.view_products',
        'create': 'inventory.manage_products',
        'update': 'inventory.manage_products',
        'partial_update': 'inventory.manage_products',
        'destroy': 'inventory.manage_products',
        'restore': 'inventory.manage_products',
    }


class ProductViewSet(SoftDeleteViewSetMixin, ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing products, barcode lookups, and bulk CSV imports.
    - Read / by_barcode: Requires `inventory.view_products`.
    - Create / Update / Soft Delete / Restore: Requires `inventory.manage_products`.
    - upload_csv: Requires `inventory.csv_import`.
    - Tenant Isolation: Scoped to request.user.shop via ShopScopedViewSetMixin.
    """
    queryset = Product.objects.all().select_related('category')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, HasPermission]
    filterset_class = ProductFilter
    search_fields = ['name', 'barcode']
    ordering_fields = ['name', 'selling_price', 'stock_quantity', 'created_at']
    ordering = ['name']
    action_permissions = {
        'list': 'inventory.view_products',
        'retrieve': 'inventory.view_products',
        'by_barcode': 'inventory.view_products',
        'create': 'inventory.manage_products',
        'update': 'inventory.manage_products',
        'partial_update': 'inventory.manage_products',
        'destroy': 'inventory.manage_products',
        'restore': 'inventory.manage_products',
        'adjust_stock': 'inventory.adjust_stock',
        'upload_csv': 'inventory.csv_import',
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

    def perform_create(self, serializer):
        """
        Record PRODUCT_CREATED audit event and INITIAL_STOCK ledger entry upon creation.
        """
        super().perform_create(serializer)
        product = serializer.instance

        if product.stock_quantity > Decimal('0.000'):
            StockMovement.objects.create(
                shop=product.shop,
                product=product,
                movement_type=StockMovement.MovementType.INITIAL_STOCK,
                quantity_change=product.stock_quantity,
                balance_after=product.stock_quantity,
                reference_type='Product',
                reference_id=str(product.public_id),
                notes="Initial stock on product creation",
                performed_by=self.request.user,
            )

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
        Record PRODUCT_PRICE_CHANGED and PRODUCT_STOCK_CHANGED audit events,
        and log ADJUSTMENT in StockMovement if stock was modified.
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
            delta = product.stock_quantity - old_stock
            StockMovement.objects.create(
                shop=product.shop,
                product=product,
                movement_type=StockMovement.MovementType.ADJUSTMENT,
                quantity_change=delta,
                balance_after=product.stock_quantity,
                reference_type='Product',
                reference_id=str(product.public_id),
                notes="Manual inventory adjustment",
                performed_by=self.request.user,
            )
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
        detail=True,
        methods=['post'],
        url_path='adjust-stock',
        permission_classes=[permissions.IsAuthenticated, HasPermission],
    )
    def adjust_stock(self, request, public_id=None):
        """
        Dedicated stock adjustment endpoint (`POST /api/inventory/products/{public_id}/adjust-stock/`),
        guarded by `inventory.adjust_stock`.
        """
        product = self.get_object()
        raw_qty = request.data.get('stock_quantity')
        if raw_qty is None:
            return Response(
                {"detail": "'stock_quantity' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_stock = Decimal(str(raw_qty))
        except InvalidOperation:
            return Response(
                {"detail": "Invalid decimal format for 'stock_quantity'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_stock < Decimal('0.000'):
            return Response(
                {"detail": "Stock quantity cannot be negative."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = str(request.data.get('notes', 'Manual stock adjustment'))[:255]
        with transaction.atomic():
            locked = Product.objects.select_for_update().get(id=product.id, shop=request.user.shop)
            old_stock = locked.stock_quantity
            if old_stock != new_stock:
                locked.stock_quantity = new_stock
                locked.save(update_fields=['stock_quantity', 'updated_at'])
                StockMovement.objects.create(
                    shop=request.user.shop,
                    product=locked,
                    movement_type=StockMovement.MovementType.ADJUSTMENT,
                    quantity_change=new_stock - old_stock,
                    balance_after=new_stock,
                    reference_type='Product',
                    reference_id=str(locked.public_id),
                    notes=notes,
                    performed_by=request.user,
                )
                log_audit_event(
                    action='PRODUCT_STOCK_CHANGED',
                    target_model='Product',
                    target_id=str(locked.public_id),
                    shop=request.user.shop,
                    actor=request.user,
                    before_state={'stock_quantity': old_stock},
                    after_state={'stock_quantity': new_stock},
                )

        return Response(self.get_serializer(locked).data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=['post'],
        url_path='upload-csv',
        permission_classes=[permissions.IsAuthenticated, HasPermission],
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
                    stock_quantity = Decimal(row_cleaned.get('stock_quantity', '0.000'))
                    reorder_level = Decimal(row_cleaned.get('reorder_level', '5.000'))
                except (InvalidOperation, ValueError):
                    errors.append(f"Row {row_idx} ({name}): Invalid numerical format in price or quantity.")
                    continue

                # Resolve or auto-create category within this shop
                category_instance = None
                if category_name:
                    category_instance, _ = Category.objects.get_or_create(
                        shop=shop,
                        name=category_name,
                        is_deleted=False,
                    )

                # Upsert Product: If barcode matches existing active product in this shop, update it
                product = None
                if barcode:
                    product = Product.objects.filter(
                        shop=shop,
                        barcode=barcode,
                        is_deleted=False,
                    ).first()

                if product:
                    old_stock = product.stock_quantity
                    # Update existing product
                    product.name = name
                    product.category = category_instance
                    product.cost_price = cost_price
                    product.selling_price = selling_price
                    product.stock_quantity = stock_quantity
                    product.reorder_level = reorder_level
                    product.save()

                    if old_stock != stock_quantity:
                        StockMovement.objects.create(
                            shop=shop,
                            product=product,
                            movement_type=StockMovement.MovementType.CSV_IMPORT,
                            quantity_change=stock_quantity - old_stock,
                            balance_after=stock_quantity,
                            reference_type='Product',
                            reference_id=str(product.public_id),
                            notes="Stock updated via CSV import",
                            performed_by=request.user,
                        )
                    updated_count += 1
                else:
                    # Create new product
                    new_product = Product.objects.create(
                        shop=shop,
                        category=category_instance,
                        name=name,
                        barcode=barcode,
                        cost_price=cost_price,
                        selling_price=selling_price,
                        stock_quantity=stock_quantity,
                        reorder_level=reorder_level,
                    )
                    if new_product.stock_quantity > Decimal('0.000'):
                        StockMovement.objects.create(
                            shop=shop,
                            product=new_product,
                            movement_type=StockMovement.MovementType.CSV_IMPORT,
                            quantity_change=new_product.stock_quantity,
                            balance_after=new_product.stock_quantity,
                            reference_type='Product',
                            reference_id=str(new_product.public_id),
                            notes="Initial stock from CSV import",
                            performed_by=request.user,
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
