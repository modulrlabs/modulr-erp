from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .authentication import clear_refresh_cookie, enforce_cookie_csrf, set_refresh_cookie
from .models import User
from .serializers import (
    CustomTokenObtainPairSerializer,
    ShopRegisterSerializer,
    ShopSerializer,
    UserMeSerializer,
)


class RegisterView(APIView):
    """
    Endpoint for public shop registration: POST /api/auth/register/

    WHY:
    Publicly accessible so new shop owners can onboard.
    Sets the refresh token in an httpOnly cookie, and conditionally includes
    the refresh token in the response body based on settings.AUTH_REFRESH_IN_BODY.
    """
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'register'

    @extend_schema(
        request=ShopRegisterSerializer,
        responses={201: ShopRegisterSerializer},
        summary="Register a new Shop & Owner account"
    )
    def post(self, request, *args, **kwargs):
        serializer = ShopRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate JWT tokens immediately
        refresh = RefreshToken.for_user(user)
        refresh['username'] = user.username
        refresh['role'] = user.role
        refresh['shop_id'] = user.shop.id if user.shop else None
        refresh['shop_name'] = user.shop.name if user.shop else None

        tokens_data = {
            "access": str(refresh.access_token),
        }
        if getattr(settings, 'AUTH_REFRESH_IN_BODY', False):
            tokens_data["refresh"] = str(refresh)

        response_data = {
            "message": "Shop and owner account registered successfully.",
            "tokens": tokens_data,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
            },
            "shop": ShopSerializer(user.shop).data if user.shop else None,
        }
        response = Response(response_data, status=status.HTTP_201_CREATED)
        set_refresh_cookie(response, refresh)
        return response


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Endpoint for user login: POST /api/auth/login/

    WHY:
    Authenticates credentials, attaches the refresh token into an httpOnly cookie,
    and strips the refresh token from the JSON body unless AUTH_REFRESH_IN_BODY is enabled.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            refresh_token = response.data.get('refresh')
            if refresh_token:
                set_refresh_cookie(response, refresh_token)
                if not getattr(settings, 'AUTH_REFRESH_IN_BODY', False):
                    response.data.pop('refresh', None)
        return response


class CookieTokenRefreshView(APIView):
    """
    Endpoint for token rotation: POST /api/auth/token/refresh/

    WHY:
    1. Calls enforce_cookie_csrf to protect against CSRF attacks.
    2. Reads refresh token from secure httpOnly cookie (with fallback if enabled).
    3. Verifies user and tenant active status.
    4. Blacklists previous refresh token (preventing replay attacks).
    5. Issues new rotated access + refresh tokens and sets updated cookie.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Rotate JWT access & refresh tokens",
        responses={200: dict, 401: dict, 403: dict}
    )
    def post(self, request, *args, **kwargs):
        # 1. Enforce CSRF validation
        enforce_cookie_csrf(request)

        # 2. Extract refresh token from cookie or payload
        raw_refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_refresh and getattr(settings, 'AUTH_REFRESH_IN_BODY', False):
            raw_refresh = request.data.get('refresh')

        if not raw_refresh:
            response = Response(
                {"detail": "Refresh token not provided in cookie or payload."},
                status=status.HTTP_401_UNAUTHORIZED
            )
            clear_refresh_cookie(response)
            return response

        # 3. Validate token and user/shop active status
        try:
            token = RefreshToken(raw_refresh)
            user_id = token.get('user_id')
            user = User.objects.select_related('shop').filter(id=user_id).first()

            if not user or not user.is_active:
                response = Response(
                    {"detail": "User account is inactive or not found."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
                clear_refresh_cookie(response)
                return response

            if user.shop and not user.shop.is_active:
                response = Response(
                    {"detail": "Shop account is inactive or suspended."},
                    status=status.HTTP_401_UNAUTHORIZED
                )
                clear_refresh_cookie(response)
                return response

            # 4. Blacklist the old refresh token
            token.blacklist()

            # 5. Issue new rotated refresh token
            new_refresh = RefreshToken.for_user(user)
            new_refresh['username'] = user.username
            new_refresh['role'] = user.role
            new_refresh['shop_id'] = user.shop.id if user.shop else None
            new_refresh['shop_name'] = user.shop.name if user.shop else None

            data = {
                "access": str(new_refresh.access_token),
            }
            if getattr(settings, 'AUTH_REFRESH_IN_BODY', False):
                data["refresh"] = str(new_refresh)

            response = Response(data, status=status.HTTP_200_OK)
            set_refresh_cookie(response, new_refresh)
            return response

        except (TokenError, InvalidToken) as e:
            response = Response(
                {"detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
            clear_refresh_cookie(response)
            return response


class LogoutView(APIView):
    """
    Endpoint for user logout: POST /api/auth/logout/

    WHY:
    Enforces CSRF check, blacklists the refresh token so it cannot be used again,
    and instructs the browser to delete the httpOnly cookie.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Logout user and clear auth cookies",
        responses={200: dict, 403: dict}
    )
    def post(self, request, *args, **kwargs):
        # 1. Enforce CSRF validation
        enforce_cookie_csrf(request)

        # 2. Retrieve refresh token and blacklist
        raw_refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_refresh and getattr(settings, 'AUTH_REFRESH_IN_BODY', False):
            raw_refresh = request.data.get('refresh')

        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except (TokenError, InvalidToken):
                pass  # Ignore if token was already blacklisted or invalid

        response = Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
        clear_refresh_cookie(response)
        return response


class CurrentUserView(APIView):
    """
    Endpoint for current authenticated user details: GET /api/auth/me/

    WHY:
    When a user refreshes the React web app or reopens the browser, the frontend
    sends its stored JWT to this endpoint to restore the active user session and
    confirm tenant status and feature flags.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses={200: UserMeSerializer},
        summary="Get active authenticated user and tenant profile"
    )
    def get(self, request, *args, **kwargs):
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
