from django.conf import settings
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .audit import log_audit_event
from .authentication import clear_refresh_cookie, enforce_cookie_csrf, set_refresh_cookie
from .filters import AuditLogFilter
from .mixins import ShopScopedViewSetMixin
from .models import AuditLog, ShopSettings, User
from .permissions import HasPermission
from .rbac import ROLE_HIERARCHY, get_request_permissions
from .serializers import (
    AuditLogSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    LoginResponseSerializer,
    ShopRegisterSerializer,
    ShopSerializer,
    ShopSettingsSerializer,
    StaffCreateSerializer,
    StaffSerializer,
    StaffUpdateSerializer,
    UserMeSerializer,
)
from .staff_utils import (
    blacklist_user_refresh_tokens,
    generate_staff_username,
    generate_temp_password,
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

    @extend_schema(responses={200: LoginResponseSerializer}, summary="Authenticate user and return JWT + permissions")
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            refresh_token = response.data.get('refresh')
            if refresh_token:
                set_refresh_cookie(response, refresh_token)
                if not getattr(settings, 'AUTH_REFRESH_IN_BODY', False):
                    response.data.pop('refresh', None)

            # Record audit event for successful login
            username = request.data.get('username')
            user = User.objects.filter(username=username).first()
            if user:
                log_audit_event(
                    action='LOGIN_SUCCESS',
                    target_model='User',
                    target_id=str(getattr(user, 'public_id', user.pk)),
                    shop=user.shop,
                    actor=user,
                    actor_username=user.username,
                    after_state={'username': user.username, 'role': user.role},
                )
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

        user = None
        if raw_refresh:
            try:
                token = RefreshToken(raw_refresh)
                user_id = token.get('user_id')
                user = User.objects.filter(id=user_id).first()
                token.blacklist()
            except (TokenError, InvalidToken):
                pass  # Ignore if token was already blacklisted or invalid

        if not user and request.user and request.user.is_authenticated:
            user = request.user

        log_audit_event(
            action='LOGOUT',
            target_model='User',
            target_id=str(getattr(user, 'public_id', user.pk)) if user else '',
            shop=getattr(user, 'shop', None),
            actor=user,
            actor_username=getattr(user, 'username', ''),
            after_state={'status': 'LOGGED_OUT'},
        )

        response = Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
        clear_refresh_cookie(response)
        return response


class AuditLogViewSet(ShopScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    RBAC-guarded ViewSet for reviewing tenant audit trails.
    - Read (GET): Requires `audit.view_all` or `audit.view_staff`.
      Users with only `audit.view_staff` (e.g. MANAGER) see staff operational actions only.
    - Writes (POST, PUT, PATCH, DELETE): Blocked at router/viewset level (ReadOnlyModelViewSet).
    - Scoping: Automatically scoped to request.user.shop via ShopScopedViewSetMixin.
    """
    queryset = AuditLog.objects.all().select_related('actor', 'shop')
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = ('audit.view_all', 'audit.view_staff')
    filterset_class = AuditLogFilter
    search_fields = ['actor_username', 'target_id', 'action']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = super().get_queryset()

        perms = get_request_permissions(self.request)
        if 'audit.view_all' not in perms:
            queryset = queryset.filter(actor__isnull=False).exclude(actor__role=User.Role.OWNER)

        return queryset


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


class ChangePasswordView(APIView):
    """
    Endpoint for authenticated users to change their password: POST /api/auth/change-password/
    Clears `must_change_password` flag and logs PASSWORD_CHANGED to AuditLog.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={200: dict},
        summary="Change current user's password"
    )
    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])

        log_audit_event(
            action='PASSWORD_CHANGED',
            target_model='User',
            target_id=str(getattr(user, 'public_id', user.pk)),
            shop=getattr(user, 'shop', None),
            actor=user,
            actor_username=user.username,
            after_state={'force_reset_cleared': True},
        )

        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


class StaffViewSet(ShopScopedViewSetMixin, viewsets.ModelViewSet):
    """
    RBAC v2 Staff Management ViewSet at `/api/staff/`.
    - Scoped strictly to `request.user.shop` via `ShopScopedViewSetMixin` (`lookup_field = 'public_id'`).
    - Guarded by `staff.manage` OR `staff.manage_cashiers_only`.
    - Enforces anti-privilege-escalation, username immutability, race-safe last-OWNER lock,
      immediate token blacklisting on deactivate/password-reset, and 405 on DELETE.
    """
    queryset = User.objects.all().order_by('id')
    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = ('staff.manage', 'staff.manage_cashiers_only')
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffCreateSerializer
        if self.action in ('partial_update', 'update'):
            return StaffUpdateSerializer
        return StaffSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        perms = get_request_permissions(self.request)
        if self.action == 'list' and 'staff.manage' not in perms:
            queryset = queryset.filter(role=User.Role.CASHIER)
        return queryset

    def _assert_actor_can_touch_role(self, request, target_role: str):
        perms = get_request_permissions(request)
        if 'staff.manage' not in perms and target_role != User.Role.CASHIER:
            raise PermissionDenied("You are only authorized to manage CASHIER accounts.")
        if ROLE_HIERARCHY.get(target_role, 0) > ROLE_HIERARCHY.get(request.user.role, 0):
            raise PermissionDenied("Cannot assign or manage a role higher than your own.")

    def create(self, request, *args, **kwargs):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_role = data['role']
        self._assert_actor_can_touch_role(request, target_role)

        shop = request.user.shop
        temp_password = generate_temp_password()

        staff_user = None
        for _ in range(5):
            username = generate_staff_username(data['first_name'])
            try:
                staff_user = User.objects.create_user(
                    username=username,
                    email=data.get('email', ''),
                    password=temp_password,
                    first_name=data['first_name'],
                    last_name=data.get('last_name', ''),
                    shop=shop,
                    role=target_role,
                    must_change_password=True,
                )
                break
            except IntegrityError:
                continue

        if staff_user is None:
            raise ValidationError({"detail": "Unable to allocate a unique username. Please retry."})

        log_audit_event(
            action='STAFF_CREATED',
            target_model='User',
            target_id=str(staff_user.public_id),
            shop=shop,
            actor=request.user,
            after_state={
                'username': staff_user.username,
                'role': staff_user.role,
                'first_name': staff_user.first_name,
                'last_name': staff_user.last_name,
                'force_reset_set': True,
            },
        )

        response_data = StaffSerializer(staff_user).data
        response_data['temporary_password'] = temp_password
        return Response(response_data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        target_user = self.get_object()
        self._assert_actor_can_touch_role(request, target_user.role)
        return Response(StaffSerializer(target_user).data, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        target_user = self.get_object()
        self._assert_actor_can_touch_role(request, target_user.role)

        serializer = StaffUpdateSerializer(target_user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        new_role = validated.get('role', target_user.role)
        old_role = target_user.role

        if new_role != old_role:
            if target_user.id == request.user.id:
                raise ValidationError({"role": "You cannot change your own role."})
            self._assert_actor_can_touch_role(request, new_role)

        shop = request.user.shop
        with transaction.atomic():
            if old_role == User.Role.OWNER and new_role != User.Role.OWNER:
                active_owners = list(
                    User.objects.select_for_update()
                    .filter(shop=shop, role=User.Role.OWNER, is_active=True)
                    .order_by('id')
                )
                if len(active_owners) <= 1:
                    raise ValidationError({
                        "detail": "Cannot demote or deactivate the last active owner of the shop."
                    })

            serializer.save()

        if old_role != target_user.role:
            log_audit_event(
                action='STAFF_ROLE_CHANGED',
                target_model='User',
                target_id=str(target_user.public_id),
                shop=shop,
                actor=request.user,
                before_state={'role': old_role},
                after_state={'role': target_user.role},
            )

        return Response(StaffSerializer(target_user).data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Staff accounts cannot be deleted. Use deactivate instead."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, public_id=None):
        target_user = self.get_object()
        self._assert_actor_can_touch_role(request, target_user.role)

        shop = request.user.shop
        with transaction.atomic():
            locked_target = User.objects.select_for_update().get(id=target_user.id, shop=shop)
            if locked_target.role == User.Role.OWNER and locked_target.is_active:
                active_owners = list(
                    User.objects.select_for_update()
                    .filter(shop=shop, role=User.Role.OWNER, is_active=True)
                    .order_by('id')
                )
                if len(active_owners) <= 1:
                    raise ValidationError({
                        "detail": "Cannot demote or deactivate the last active owner of the shop."
                    })

            locked_target.is_active = False
            locked_target.save(update_fields=['is_active'])

        blacklist_user_refresh_tokens(locked_target)

        log_audit_event(
            action='STAFF_DEACTIVATED',
            target_model='User',
            target_id=str(locked_target.public_id),
            shop=shop,
            actor=request.user,
            before_state={'is_active': True},
            after_state={'is_active': False},
        )

        return Response(StaffSerializer(locked_target).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reactivate')
    def reactivate(self, request, public_id=None):
        target_user = self.get_object()
        self._assert_actor_can_touch_role(request, target_user.role)

        target_user.is_active = True
        target_user.save(update_fields=['is_active'])

        log_audit_event(
            action='STAFF_REACTIVATED',
            target_model='User',
            target_id=str(target_user.public_id),
            shop=request.user.shop,
            actor=request.user,
            before_state={'is_active': False},
            after_state={'is_active': True},
        )

        return Response(StaffSerializer(target_user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, public_id=None):
        target_user = self.get_object()
        self._assert_actor_can_touch_role(request, target_user.role)

        temp_password = generate_temp_password()
        target_user.set_password(temp_password)
        target_user.must_change_password = True
        target_user.save(update_fields=['password', 'must_change_password'])

        blacklist_user_refresh_tokens(target_user)

        log_audit_event(
            action='STAFF_PASSWORD_RESET',
            target_model='User',
            target_id=str(target_user.public_id),
            shop=request.user.shop,
            actor=request.user,
            after_state={
                'username': target_user.username,
                'force_reset_set': True,
            },
        )

        return Response(
            {
                'public_id': str(target_user.public_id),
                'username': target_user.username,
                'temporary_password': temp_password,
                'must_change_password': target_user.must_change_password,
            },
            status=status.HTTP_200_OK,
        )


class ShopSettingsView(generics.RetrieveUpdateAPIView):
    """
    Owner-only endpoint for viewing and updating ShopSettings (`GET` & `PATCH /api/core/shop-settings/`).
    """
    serializer_class = ShopSettingsSerializer
    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = 'settings.manage_shop'
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        settings_obj, _ = ShopSettings.objects.get_or_create(shop_id=self.request.user.shop_id)
        return settings_obj

    def perform_update(self, serializer):
        instance = self.get_object()
        tracked_fields = (
            'managers_can_edit_products',
            'managers_can_view_cost_price',
            'managers_can_view_profit',
            'managers_can_manage_purchasing',
            'managers_can_manage_cashiers',
            'cashier_max_discount_pct',
            'tax_mode',
            'tax_rate_pct',
            'tax_label',
        )
        before_state = {field: getattr(instance, field) for field in tracked_fields}
        updated = serializer.save()
        after_state = {field: getattr(updated, field) for field in tracked_fields}

        log_audit_event(
            action='SHOP_SETTINGS_UPDATED',
            target_model='ShopSettings',
            target_id=str(self.request.user.shop.public_id),
            shop=self.request.user.shop,
            actor=self.request.user,
            before_state=before_state,
            after_state=after_state,
        )
