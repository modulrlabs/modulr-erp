from rest_framework import permissions


class IsShopOwner(permissions.BasePermission):
    """
    Strict permission ensuring that only users with role='OWNER' can access the view.

    WHY:
    Sensitive operations like viewing business analytics or immutable audit logs
    must be strictly restricted to shop owners.
    """
    message = "Only shop owners are authorized to perform this operation."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'is_owner', False)
        )
