from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .rbac import get_effective_permissions


class ShopJWTAuthentication(JWTAuthentication):
    """
    DB-backed JWT Authentication that validates live user & tenant state on every request
    and resolves effective RBAC v2 permissions once per request.
    """

    def get_user(self, validated_token):
        User = get_user_model()
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken("Token contained no recognizable user identification") from exc

        try:
            user = User.objects.select_related('shop__settings').get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except User.DoesNotExist as exc:
            raise AuthenticationFailed("User not found", code="user_not_found") from exc

        if not user.is_active:
            raise AuthenticationFailed("User is inactive", code="user_inactive")

        if user.shop is None or not user.shop.is_active:
            raise AuthenticationFailed(
                "Active shop membership required",
                code="shop_inactive",
            )

        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _validated_token = result
            request._effective_permissions = get_effective_permissions(user)
        return result


def _normalize_origin(url: str) -> str:
    """
    Extracts the scheme + netloc from a URL (e.g. 'http://localhost:5173/path' -> 'http://localhost:5173').
    """
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    return url.rstrip('/')


def enforce_cookie_csrf(request):
    """
    Validates CSRF defenses for state-changing cookie-authenticated requests.

    WHY:
    1. Custom Header Requirement:
       Browsers forbid cross-origin scripts from setting custom headers unless explicitly
       allowed by CORS pre-flight. Requiring 'X-Requested-With: XMLHttpRequest' completely
       neutralizes classic cross-site form/image request forgery.

    2. Origin / Referer Verification:
       When present, verifies that the requesting origin matches settings.CSRF_TRUSTED_ORIGINS.
    """
    # 1. Require X-Requested-With header
    x_requested_with = request.headers.get('X-Requested-With')
    if x_requested_with != 'XMLHttpRequest':
        raise PermissionDenied("Missing or invalid X-Requested-With header.")

    # 2. Check Origin or Referer when present
    origin = request.headers.get('Origin')
    referer = request.headers.get('Referer')

    trusted_origins = {
        _normalize_origin(o) for o in getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
    }
    trusted_origins.update({
        _normalize_origin(o) for o in getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
    })

    candidate_url = origin or referer
    if candidate_url:
        normalized_candidate = _normalize_origin(candidate_url)
        if normalized_candidate not in trusted_origins:
            raise PermissionDenied(f"Untrusted origin/referer: '{candidate_url}'.")


def set_refresh_cookie(response, refresh_token):
    """
    Attaches the JWT refresh token as a secure, httpOnly cookie on the response.

    WHY:
    Storing refresh tokens in httpOnly cookies prevents XSS (Cross-Site Scripting)
    attacks from stealing the persistent session token via JavaScript (document.cookie).
    """
    max_age = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=str(refresh_token),
        max_age=max_age,
        httponly=True,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


def clear_refresh_cookie(response):
    """
    Deletes the refresh token cookie upon logout or token invalidation.
    """
    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        samesite=settings.COOKIE_SAMESITE,
    )
