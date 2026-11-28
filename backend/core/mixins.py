from django.db import IntegrityError
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .audit import log_audit_event
from .permissions import HasPermission


class ShopScopedViewSetMixin:
    """
    Mixin to enforce systematic row-level tenant isolation across DRF ViewSets.

    WHY:
    In a multi-tenant SaaS architecture (ARCHITECTURE.md Rule 1), ensuring that one
    tenant cannot access or mutate another tenant's data must not rely on developers
    remembering to add `.filter(shop=request.user.shop)` to every single view query.

    This mixin provides systematic guarantees:
    1. Authentication & Active Shop Verification:
       Denies access with 403 PermissionDenied if the user is unauthenticated or
       if their assigned shop subscription has been deactivated (`is_active=False`).
    2. Query Scoping:
       Automatically filters `super().get_queryset()` to `shop=request.user.shop`.
    3. Creation Scoping:
       Automatically binds `shop=request.user.shop` in `perform_create()`, preventing
       clients from tampering with tenant ownership headers or body payloads.
    4. UUID Public ID Lookups:
       Sets `lookup_field = 'public_id'` and `lookup_url_kwarg = 'public_id'` so
       detail routes (/items/{public_id}/) resolve by non-sequential UUIDs instead of
       sequential integer PKs, preventing ID enumeration attacks.
    """

    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"

    def get_queryset(self):
        """
        Enforce that querysets are strictly constrained to the authenticated user's shop.
        """
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            raise PermissionDenied("Authentication required.")

        shop = getattr(user, "shop", None)
        if not shop or not shop.is_active:
            raise PermissionDenied("Active shop membership required.")

        qs = super().get_queryset().filter(shop=shop)
        if hasattr(qs.model, "is_deleted") and getattr(self, "action", None) != "restore":
            qs = qs.filter(is_deleted=False)
        return qs

    def perform_create(self, serializer):
        """
        Securely attach the authenticated user's shop to any newly created model instance.
        """
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            raise PermissionDenied("Authentication required.")

        shop = getattr(user, "shop", None)
        if not shop or not shop.is_active:
            raise PermissionDenied("Active shop membership required.")

        serializer.save(shop=shop)


class SoftDeleteViewSetMixin:
    """
    Reusable soft-delete and restore behavior for ViewSets whose models inherit
    `SoftDeleteModelMixin` (`Category`, `Product`, `Customer`).
    """

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.deleted_by = self.request.user
        instance.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])

        log_audit_event(
            action="SOFT_DELETED",
            target_model=instance.__class__.__name__,
            target_id=str(instance.public_id),
            shop=self.request.user.shop,
            actor=self.request.user,
            before_state={"is_deleted": False},
            after_state={"is_deleted": True},
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="restore",
        permission_classes=[permissions.IsAuthenticated, HasPermission],
    )
    def restore(self, request, public_id=None):
        instance = self.get_object()
        if not instance.is_deleted:
            raise ValidationError({"detail": "This record is not deleted."})

        instance.is_deleted = False
        instance.deleted_at = None
        instance.deleted_by = None
        try:
            instance.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])
        except IntegrityError as exc:
            raise ValidationError({
                "detail": (
                    "Cannot restore: an active record with a conflicting unique "
                    "value already exists."
                )
            }) from exc

        log_audit_event(
            action="RESTORED",
            target_model=instance.__class__.__name__,
            target_id=str(instance.public_id),
            shop=request.user.shop,
            actor=request.user,
            before_state={"is_deleted": True},
            after_state={"is_deleted": False},
        )

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


def validate_tenant_fk(obj, shop, field_name="resource"):
    """
    Validates that a foreign key instance belongs to the authenticated user's shop.

    WHY (Preventing IDOR & Cross-Tenant Information Leakage):
    If Tenant A submits a foreign key ID (e.g., category_id or customer_id) belonging
    to Tenant B, we must reject the request with 400 Bad Request.
    Importantly, returning 'Category with ID 5 belongs to another shop' leaks the
    existence of private records across tenants. We return a generic message:
    'Invalid {field_name} selection.'
    """
    if obj is None:
        return obj

    obj_shop_id = getattr(obj, "shop_id", None)
    if obj_shop_id is None and hasattr(obj, "shop"):
        obj_shop_id = getattr(obj.shop, "id", None)

    tenant_shop_id = getattr(shop, "id", None) if shop is not None else None

    if obj_shop_id != tenant_shop_id or tenant_shop_id is None:
        raise serializers.ValidationError(f"Invalid {field_name} selection.")

    return obj


class TenantPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """
    A PrimaryKeyRelatedField that strictly bounds selectable choices to the
    requesting user's shop, preventing IDOR and cross-tenant leakage.

    WHY:
    When DRF validates an incoming PK, it queries `get_queryset()`. By scoping
    `get_queryset()` to the request user's shop, foreign keys from other shops
    are treated as non-existent and rejected with a generic message.
    """

    default_error_messages = {
        "does_not_exist": "Invalid {field_name} selection.",
        "incorrect_type": "Incorrect type. Expected pk value, received {data_type}.",
    }

    def __init__(self, field_name="resource", **kwargs):
        self.field_name = field_name
        super().__init__(**kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            shop = getattr(request.user, "shop", None)
            if shop:
                return queryset.filter(shop=shop)
        return queryset.none()

    def fail(self, key, **kwargs):
        if key == "does_not_exist":
            kwargs.setdefault("field_name", self.field_name)
        super().fail(key, **kwargs)
