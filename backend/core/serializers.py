from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Shop, User


class ShopSerializer(serializers.ModelSerializer):
    """
    Serializer for the Shop (Tenant) model.
    """
    class Meta:
        model = Shop
        fields = (
            'id',
            'public_id',
            'name',
            'address',
            'phone',
            'is_active',
            'enable_credit_module',
            'enable_whatsapp_alerts',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'public_id', 'created_at', 'updated_at')


class UserMeSerializer(serializers.ModelSerializer):
    """
    Serializer to represent the currently authenticated user and their tenant shop.
    Used by the GET /api/auth/me/ endpoint.
    """
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'is_owner',
            'is_cashier',
            'shop',
        )
        read_only_fields = ('id', 'role', 'is_owner', 'is_cashier', 'shop')


class ShopRegisterSerializer(serializers.Serializer):
    """
    Serializer for registering a brand-new Shop and its founding Owner User.

    WHY:
    A SaaS shop onboarding process requires creating two distinct database entities:
    1. The Shop (tenant)
    2. The User (first user with role='OWNER')
    Both must be created together, or neither should be created (All-or-Nothing).
    """
    # Shop fields
    shop_name = serializers.CharField(
        max_length=255,
        required=True,
        help_text="The trading name of the shop."
    )
    address = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Physical location of the shop."
    )
    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default="",
        help_text="Contact telephone number."
    )

    # Owner User fields
    username = serializers.CharField(
        max_length=150,
        required=True,
        help_text="Unique login username for the shop owner."
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Owner email address."
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Secure password (minimum 8 characters)."
    )
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        """
        WHY: Ensure username uniqueness before entering the database transaction.
        """
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_password(self, value):
        """
        WHY: Leverage Django's configured auth password validators to ensure security.
        """
        validate_password(value)
        return value

    def create(self, validated_data):
        """
        Creates the Shop and Owner User in a single atomic database transaction.

        WHY transaction.atomic():
        If the shop is created but user creation fails (e.g. database constraint or invalid field),
        the database automatically ROLLS BACK, deleting the orphaned Shop.
        This guarantees database consistency and prevents 'ghost tenants' with no owners.
        """
        shop_name = validated_data['shop_name']
        address = validated_data.get('address', '')
        phone = validated_data.get('phone', '')

        username = validated_data['username']
        email = validated_data.get('email', '')
        password = validated_data['password']
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')

        with transaction.atomic():
            # 1. Create the tenant Shop
            shop = Shop.objects.create(
                name=shop_name,
                address=address,
                phone=phone,
                is_active=True,
                enable_credit_module=False,
                enable_whatsapp_alerts=False,
            )

            # 2. Create the founding User with OWNER role attached to this Shop
            # WHY create_user(): It automatically hashes passwords with PBKDF2/Argon2.
            # Never use User.objects.create(password=raw_password) which stores plain text!
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                shop=shop,
                role=User.Role.OWNER,
            )

            return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT login serializer that enriches the login response with tenant shop details,
    staff role, and modular feature flags.

    WHY:
    By including the shop details, role, and feature flags directly in the login response,
    the React frontend receives everything it needs to configure UI navigation, permissions,
    and feature switches in one single network roundtrip, without needing extra API calls.
    """

    @classmethod
    def get_token(cls, user):
        """
        WHY: Custom claims embedded in the JWT payload allow downstream microservices
        or client decoders to read the tenant id and role directly from the token.
        """
        token = super().get_token(user)

        token['username'] = user.username
        token['role'] = user.role
        token['shop_id'] = user.shop.id if user.shop else None
        token['shop_name'] = user.shop.name if user.shop else None

        return token

    def validate(self, attrs):
        """
        Validates user credentials and enforces tenant-level access restrictions.
        """
        # super().validate verifies username and password against Django's auth backend
        data = super().validate(attrs)
        user = self.user

        # WHY: Check if the individual user account is active
        if not user.is_active:
            raise serializers.ValidationError({"detail": "This user account is inactive."})

        # WHY: Multi-Tenant Suspension Check.
        # If a shop owner hasn't paid their SaaS invoice, the shop is marked is_active=False.
        # Cashiers and staff belonging to an inactive shop must be blocked from logging in.
        if user.shop and not user.shop.is_active:
            raise serializers.ValidationError({
                "detail": "This shop subscription is inactive or suspended. Please contact support."
            })

        # Inject user and tenant details into the response payload
        data['user'] = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
        }

        if user.shop:
            data['shop'] = {
                'id': user.shop.id,
                'public_id': str(user.shop.public_id),
                'name': user.shop.name,
                'address': user.shop.address,
                'phone': user.shop.phone,
                'features': {
                    'enable_credit_module': user.shop.enable_credit_module,
                    'enable_whatsapp_alerts': user.shop.enable_whatsapp_alerts,
                }
            }
        else:
            data['shop'] = None

        return data
