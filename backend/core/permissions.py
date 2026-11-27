from django.core.cache import cache
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from .audit import log_audit_event
from .rbac import get_request_permissions

PASSWORD_CHANGE_EXEMPT_PATHS = frozenset({
    '/api/auth/change-password/',
    '/api/auth/logout/',
    '/api/auth/me/',
    '/api/auth/token/refresh/',
})


class EnforcePasswordChange(permissions.BasePermission):
    """
    Blocks authenticated users with `must_change_password=True` from accessing
    any endpoint other than the 4 exempt auth lifecycle endpoints.
    """

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if (
            user
            and user.is_authenticated
            and getattr(user, 'must_change_password', False)
            and request.path not in PASSWORD_CHANGE_EXEMPT_PATHS
        ):
            raise PermissionDenied({
                'detail': 'Password change required before accessing this resource.',
                'code': 'password_change_required',
            })
        return True


class HasPermission(permissions.BasePermission):
    """
    RBAC v2 permission class supporting:
    - Single permission or any_of tuple on `view.required_permission`
    - Per-action mapping on `view.action_permissions`
    - Factory helpers `HasPermission.require(...)` and `HasPermission.any_of(...)`
    - Enforces `must_change_password` and rate-limits 403 PERMISSION_DENIED audit logs.
    """

    message = 'You do not have permission to perform this action.'
    required_perms: tuple[str, ...] | None = None

    @classmethod
    def require(cls, permission_code: str):
        return type(
            f'HasPermission_{permission_code.replace(".", "_")}',
            (cls,),
            {'required_perms': (permission_code,)},
        )

    @classmethod
    def any_of(cls, *permission_codes: str):
        return type(
            'HasPermission_AnyOf',
            (cls,),
            {'required_perms': tuple(permission_codes)},
        )

    def _resolve_required_permissions(self, view) -> tuple[str, ...]:
        if self.required_perms is not None:
            return self.required_perms

        action_map = getattr(view, 'action_permissions', None)
        action = getattr(view, 'action', None)
        if action_map is not None and action in action_map:
            spec = action_map[action]
            return (spec,) if isinstance(spec, str) else tuple(spec)

        view_perm = getattr(view, 'required_permission', None)
        if view_perm is not None:
            return (view_perm,) if isinstance(view_perm, str) else tuple(view_perm)

        return ()

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        # Ensure must_change_password is enforced even when views override DEFAULT_PERMISSION_CLASSES
        EnforcePasswordChange().has_permission(request, view)

        shop = getattr(user, 'shop', None)
        if not shop or not shop.is_active:
            raise PermissionDenied('Active shop membership required.')

        required = self._resolve_required_permissions(view)
        if not required:
            return False

        effective_perms = get_request_permissions(request)
        if any(perm in effective_perms for perm in required):
            return True

        # Rate-limit PERMISSION_DENIED audit logs to 1 per (user_id, path) per 60 seconds
        cache_key = f'perm_denied_audit:{user.id}:{request.path}'
        if cache.add(cache_key, 1, timeout=60):
            log_audit_event(
                action='PERMISSION_DENIED',
                target_model=view.__class__.__name__,
                target_id=request.path[:64],
                shop=getattr(user, 'shop', None),
                actor=user,
                after_state={
                    'path': request.path,
                    'method': request.method,
                    'required_permission': ' | '.join(required),
                },
            )

        return False


class IsShopOwner(permissions.BasePermission):
    """
    Legacy helper: Strict permission ensuring only users with role='OWNER' can access.
    """
    message = "Only shop owners are authorized to perform this operation."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'is_owner', False)
        )
