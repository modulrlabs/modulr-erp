from rest_framework import permissions


class IsShopOwner(permissions.BasePermission):
    """
    Strict permission ensuring that only users with role='OWNER' can access
    the view (e.g. Owner Dashboard Analytics).

    WHY:
    Cashiers must not have access to shop financial metrics, gross profits,
    cash collections, or high-level business analytics.
    """
    message = "Access restricted: Only shop owners can view business analytics."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'is_owner', False)
        )


class IsCreditModuleEnabled(permissions.BasePermission):
    """
    Permission class that enforces the 'enable_credit_module' feature flag on the Shop model.

    WHY:
    Enforces SaaS Modularity (ARCHITECTURE.md Rule 2).
    Shops on the basic POS plan cannot access Customer Credit Ledgers or PD Cheque
    management unless the shop owner subscribes to the Credit module.
    """
    message = (
        "The Customer Credit & Cheque module is not enabled for your shop subscription. "
        "Please contact support to upgrade."
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        shop = getattr(request.user, 'shop', None)
        if not shop:
            return False

        # Return True only if shop has enable_credit_module=True
        return bool(shop.enable_credit_module)
