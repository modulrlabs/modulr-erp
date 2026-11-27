from decimal import Decimal

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AuditLog, Shop, User
from core.rbac import get_effective_permissions
from inventory.models import Category, Product
from sales.models import Invoice


class RBACEnforcementTests(APITestCase):
    """
    Integration tests for RBAC v2 Step 4a-2 enforcement:
    - DB-backed ShopJWTAuthentication & immediate deactivation
    - must_change_password enforcement & exempt endpoints
    - assertNumQueries proving zero N+1 queries with select_related('shop__settings')
    - Field-level cost_price stripping
    - Cashier OWN-only invoice scoping
    - Rate-limited 403 PERMISSION_DENIED audit logging
    - Additive login & /me payloads
    """

    def setUp(self):
        cache.clear()
        self.shop = Shop.objects.create(
            name="Enforcement Mart",
            enable_credit_module=True,
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="enf_owner",
            password="Password123!",
            shop=self.shop,
            role=User.Role.OWNER,
        )
        self.manager = User.objects.create_user(
            username="enf_manager",
            password="Password123!",
            shop=self.shop,
            role=User.Role.MANAGER,
        )
        self.cashier_a = User.objects.create_user(
            username="enf_cashier_a",
            password="Password123!",
            shop=self.shop,
            role=User.Role.CASHIER,
        )
        self.cashier_b = User.objects.create_user(
            username="enf_cashier_b",
            password="Password123!",
            shop=self.shop,
            role=User.Role.CASHIER,
        )
        self.inventory_manager = User.objects.create_user(
            username="enf_inv_mgr",
            password="Password123!",
            shop=self.shop,
            role=User.Role.INVENTORY_MANAGER,
        )
        self.accountant = User.objects.create_user(
            username="enf_accountant",
            password="Password123!",
            shop=self.shop,
            role=User.Role.ACCOUNTANT,
        )
        self.category = Category.objects.create(shop=self.shop, name="Beverages")
        self.product = Product.objects.create(
            shop=self.shop,
            category=self.category,
            name="Ceylon Tea",
            barcode="1234567890123",
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            stock_quantity=Decimal('20.000'),
        )

    def _get_access_token(self, user: User) -> str:
        return str(RefreshToken.for_user(user).access_token)

    def test_deactivated_user_access_token_rejected_immediately(self):
        """Reusing an existing valid access token after user.is_active=False returns 401."""
        token = self._get_access_token(self.cashier_a)
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        res_ok = self.client.get('/api/inventory/products/', **auth_header)
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

        # Deactivate user in DB
        self.cashier_a.is_active = False
        self.cashier_a.save(update_fields=['is_active'])

        res_blocked = self.client.get('/api/inventory/products/', **auth_header)
        self.assertEqual(res_blocked.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_must_change_password_enforcement_and_exempt_endpoints(self):
        """
        Users with must_change_password=True get 403 (code=password_change_required) on API
        endpoints, while /me/, /token/refresh/, /logout/, and /change-password/ remain accessible.
        """
        self.cashier_a.must_change_password = True
        self.cashier_a.save(update_fields=['must_change_password'])

        refresh = RefreshToken.for_user(self.cashier_a)
        access_token = str(refresh.access_token)
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {access_token}'}

        # Blocked on normal endpoints
        res_products = self.client.get('/api/inventory/products/', **auth_header)
        self.assertEqual(res_products.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_products.data['code'], 'password_change_required')

        # Exempt 1: /api/auth/me/
        res_me = self.client.get('/api/auth/me/', **auth_header)
        self.assertEqual(res_me.status_code, status.HTTP_200_OK)
        self.assertTrue(res_me.data['must_change_password'])

        # Exempt 2: /api/auth/change-password/
        res_pw = self.client.post(
            '/api/auth/change-password/',
            data={
                'current_password': 'Password123!',
                'new_password': 'NewStrongPassword456!',
            },
            format='json',
            **auth_header,
        )
        self.assertEqual(res_pw.status_code, status.HTTP_200_OK)

        # AuditLog recorded PASSWORD_CHANGED
        self.assertTrue(
            AuditLog.objects.filter(
                action='PASSWORD_CHANGED',
                actor=self.cashier_a,
            ).exists()
        )

        # Access restored immediately after changing password
        res_products_after = self.client.get('/api/inventory/products/', **auth_header)
        self.assertEqual(res_products_after.status_code, status.HTTP_200_OK)

        # Exempt 3 & 4: /api/auth/token/refresh/ and /api/auth/logout/
        self.cashier_a.must_change_password = True
        self.cashier_a.save(update_fields=['must_change_password'])
        self.client.cookies['modulr_refresh_token'] = str(refresh)
        res_refresh = self.client.post(
            '/api/auth/token/refresh/',
            {},
            format='json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_refresh.status_code, status.HTTP_200_OK)

        self.client.cookies['modulr_refresh_token'] = res_refresh.cookies['modulr_refresh_token'].value
        res_logout = self.client.post(
            '/api/auth/logout/',
            {},
            format='json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_logout.status_code, status.HTTP_200_OK)

    def test_num_queries_no_n_plus_one_on_authenticated_request(self):
        """
        ShopJWTAuthentication select_related('shop__settings') + per-request permission caching
        keeps GET /api/inventory/products/ at exactly 2 SQL queries for MANAGER.
        """
        token = self._get_access_token(self.manager)
        with self.assertNumQueries(2):
            res = self.client.get(
                '/api/inventory/products/',
                HTTP_AUTHORIZATION=f'Bearer {token}',
            )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_cost_price_field_stripping_by_permission(self):
        """cost_price is absent for CASHIER and present for OWNER, INVENTORY_MANAGER, and ACCOUNTANT."""
        # Cashier: absent
        self.client.force_authenticate(user=self.cashier_a)
        res_cashier = self.client.get('/api/inventory/products/')
        self.assertEqual(res_cashier.status_code, status.HTTP_200_OK)
        self.assertNotIn('cost_price', res_cashier.data[0])

        # Owner, Inventory Manager, Accountant: present
        for user in (self.owner, self.inventory_manager, self.accountant):
            self.client.force_authenticate(user=user)
            res = self.client.get('/api/inventory/products/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertIn('cost_price', res.data[0], f"Expected cost_price for {user.role}")

    def test_cashier_sees_only_own_invoices(self):
        """Cashiers see only their own invoices; OWNER sees all shop invoices."""
        inv_a = Invoice.objects.create(
            shop=self.shop,
            invoice_number='INV-CA-001',
            cashier=self.cashier_a,
            subtotal=Decimal('150.00'),
            total_amount=Decimal('150.00'),
            amount_paid=Decimal('150.00'),
        )
        inv_b = Invoice.objects.create(
            shop=self.shop,
            invoice_number='INV-CB-001',
            cashier=self.cashier_b,
            subtotal=Decimal('300.00'),
            total_amount=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
        )
        inv_owner = Invoice.objects.create(
            shop=self.shop,
            invoice_number='INV-OWN-001',
            cashier=self.owner,
            subtotal=Decimal('450.00'),
            total_amount=Decimal('450.00'),
            amount_paid=Decimal('450.00'),
        )

        # Cashier A sees only inv_a
        self.client.force_authenticate(user=self.cashier_a)
        res_list = self.client.get('/api/sales/invoices/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        returned_numbers = {item['invoice_number'] for item in res_list.data}
        self.assertEqual(returned_numbers, {'INV-CA-001'})

        # Direct retrieve of Cashier B's invoice returns 404
        res_detail_b = self.client.get(f'/api/sales/invoices/{inv_b.public_id}/')
        self.assertEqual(res_detail_b.status_code, status.HTTP_404_NOT_FOUND)

        # Owner sees all 3 invoices
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get('/api/sales/invoices/')
        self.assertEqual(res_owner.status_code, status.HTTP_200_OK)
        owner_numbers = {item['invoice_number'] for item in res_owner.data}
        self.assertEqual(
            owner_numbers,
            {inv_a.invoice_number, inv_b.invoice_number, inv_owner.invoice_number},
        )

    def test_403_audit_log_rate_limited_per_user_and_endpoint(self):
        """Hitting a forbidden endpoint 3 times rapidly creates only 1 PERMISSION_DENIED AuditLog."""
        cache.clear()
        self.client.force_authenticate(user=self.cashier_a)

        for _ in range(3):
            res = self.client.get('/api/sales/dashboard/')
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        logs = AuditLog.objects.filter(
            action='PERMISSION_DENIED',
            actor=self.cashier_a,
            target_id='/api/sales/dashboard/',
        )
        self.assertEqual(logs.count(), 1)

    def test_login_and_me_include_permissions_and_must_change_password(self):
        """POST /api/auth/login/ and GET /api/auth/me/ include sorted permissions and must_change_password."""
        login_res = self.client.post(
            '/api/auth/login/',
            data={'username': 'enf_manager', 'password': 'Password123!'},
            format='json',
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_res.data)
        self.assertIn('user', login_res.data)
        self.assertIn('shop', login_res.data)
        self.assertIn('permissions', login_res.data)
        self.assertIn('must_change_password', login_res.data)
        self.assertFalse(login_res.data['must_change_password'])
        self.assertEqual(
            login_res.data['permissions'],
            sorted(get_effective_permissions(self.manager)),
        )

        access_token = login_res.data['access']
        me_res = self.client.get(
            '/api/auth/me/',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertIn('permissions', me_res.data)
        self.assertIn('must_change_password', me_res.data)
        self.assertEqual(
            me_res.data['permissions'],
            sorted(get_effective_permissions(self.manager)),
        )
