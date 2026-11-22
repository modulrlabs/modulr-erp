from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    CustomTokenObtainPairSerializer,
    ShopRegisterSerializer,
    ShopSerializer,
    UserMeSerializer,
)


class RegisterView(APIView):
    """
    Endpoint for public shop registration: POST /api/auth/register/

    WHY permission_classes = [permissions.AllowAny]:
    This endpoint must be publicly accessible so new business owners can register
    and onboard themselves without an existing token.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=ShopRegisterSerializer,
        responses={201: ShopRegisterSerializer},
        summary="Register a new Shop & Owner account"
    )
    def post(self, request, *args, **kwargs):
        serializer = ShopRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # WHY: Generate JWT tokens immediately upon registration.
        # This provides a smooth user experience where the user doesn't have to
        # re-type their credentials immediately after registering.
        refresh = RefreshToken.for_user(user)

        # Inject custom claims so token payload matches CustomTokenObtainPairSerializer
        refresh['username'] = user.username
        refresh['role'] = user.role
        refresh['shop_id'] = user.shop.id if user.shop else None
        refresh['shop_name'] = user.shop.name if user.shop else None

        response_data = {
            "message": "Shop and owner account registered successfully.",
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
            },
            "shop": ShopSerializer(user.shop).data if user.shop else None,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Endpoint for public user login: POST /api/auth/login/

    WHY:
    Uses CustomTokenObtainPairSerializer to return JWT tokens alongside user profile,
    tenant details, and active feature flags in a single JSON payload.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer


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
