from rest_framework import permissions


class IsShopOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission for Inventory operations:
    - CASHIER & OWNER: Can view (GET, HEAD, OPTIONS) products and categories.
    - OWNER ONLY: Can create (POST), edit (PUT, PATCH), or delete (DELETE) inventory.

    WHY:
    In a retail store, cashiers need to search products and scan barcodes to ring up sales.
    However, cashiers must NEVER be allowed to alter retail prices, delete stock,
    or create unauthorized products.
    """
    message = "Only shop owners are authorized to create, modify, or delete inventory items."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Read-only operations allowed for any authenticated staff member (Cashier or Owner)
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write operations strictly restricted to shop owners
        return bool(getattr(request.user, 'is_owner', False))


class IsShopOwner(permissions.BasePermission):
    """
    Strict permission allowing access exclusively to shop owners.
    Used for sensitive operations like bulk CSV catalog imports.
    """
    message = "This administrative operation is restricted exclusively to shop owners."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'is_owner', False)
        )
