import inspect
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import status
from rest_framework.test import APITestCase

import core.views as core_views
import inventory.serializers as inv_serializers
import sales.serializers as sales_serializers
import sales.views as sales_views
from core.models import AuditLog, Shop, User
from core.rbac import ACTIVE_PERMISSIONS, PERMISSIONS, RESERVED_PERMISSIONS
from inventory.models import Category, Product
from sales.models import Customer, Invoice, InvoiceItem


class FiveRolePermissionMatrixTests(APITestCase):
    """
    Step 4a-4 verification:
    1. 5-Role Permission Matrix across all protected endpoints
    2. Owner ShopSettings toggle dynamics & AuditLog
    3. Role-specific GET /api/dashboard/summary/ section presence/absence
    4. Registry enforcement check across all active permissions
    """

    def setUp(self):
        self.shop = Shop.objects.create(
            name="Matrix Mart",
            enable_credit_module=True,
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="mx_owner", password="Password123!", shop=self.shop, role=User.Role.OWNER
        )
        self.manager = User.objects.create_user(
            username="mx_manager", password="Password123!", shop=self.shop, role=User.Role.MANAGER
        )
        self.cashier = User.objects.create_user(
            username="mx_cashier", password="Password123!", shop=self.shop, role=User.Role.CASHIER
        )
        self.inv_mgr = User.objects.create_user(
            username="mx_inv",
            password="Password123!",
            shop=self.shop,
            role=User.Role.INVENTORY_MANAGER,
        )
        self.accountant = User.objects.create_user(
            username="mx_acc", password="Password123!", shop=self.shop, role=User.Role.ACCOUNTANT
        )

        self.category = Category.objects.create(shop=self.shop, name="Groceries")
        self.product = Product.objects.create(
            shop=self.shop,
            category=self.category,
            name="Basmati Rice",
            barcode="8880001112223",
            cost_price=Decimal('200.00'),
            selling_price=Decimal('300.00'),
            stock_quantity=Decimal('50.000'),
            reorder_level=Decimal('5.000'),
        )
        self.customer = Customer.objects.create(
            shop=self.shop,
            name="Nimali",
            phone="0771234567",
        )
        self.invoice = Invoice.objects.create(
            shop=self.shop,
            invoice_number="INV-MX-0001",
            cashier=self.cashier,
            subtotal=Decimal('300.00'),
            total_amount=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
        )
        InvoiceItem.objects.create(
            shop=self.shop,
            invoice=self.invoice,
            product=self.product,
            quantity=Decimal('1.000'),
            unit_price=Decimal('300.00'),
            cost_price_at_sale=Decimal('200.00'),
            line_total=Decimal('300.00'),
        )

    def _assert_matrix(self, method, url, expected_by_role, data=None, fmt='json'):
        roles = {
            'OWNER': self.owner,
            'MANAGER': self.manager,
            'CASHIER': self.cashier,
            'INVENTORY_MANAGER': self.inv_mgr,
            'ACCOUNTANT': self.accountant,
        }
        for role_name, user in roles.items():
            self.client.force_authenticate(user=user)
            payload = data() if callable(data) else data
            res = getattr(self.client, method)(url, data=payload, format=fmt)
            expected = expected_by_role[role_name]
            if isinstance(expected, tuple):
                self.assertIn(
                    res.status_code,
                    expected,
                    f"{method.upper()} {url} for {role_name}: got {res.status_code}, expected {expected}",
                )
            else:
                self.assertEqual(
                    res.status_code,
                    expected,
                    f"{method.upper()} {url} for {role_name}: got {res.status_code}, expected {expected}",
                )

    def test_five_role_permission_matrix(self):
        """Every protected endpoint enforces exact 5-role allow/403 behavior."""
        self._assert_matrix('get', '/api/inventory/products/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 200, 'INVENTORY_MANAGER': 200, 'ACCOUNTANT': 200,
        })
        self._assert_matrix('post', '/api/inventory/products/', {
            'OWNER': 201, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 201, 'ACCOUNTANT': 403,
        }, data=lambda: {'name': f'Item-{User.objects.count()}', 'selling_price': '100.00'})
        self._assert_matrix('post', f'/api/inventory/products/{self.product.public_id}/adjust-stock/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 403, 'INVENTORY_MANAGER': 200, 'ACCOUNTANT': 403,
        }, data={'stock_quantity': '45.000'})
        self._assert_matrix('get', '/api/inventory/categories/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 200, 'INVENTORY_MANAGER': 200, 'ACCOUNTANT': 200,
        })
        cat_counter = {'n': 0}

        def next_cat():
            cat_counter['n'] += 1
            return {'name': f"Cat-{cat_counter['n']}"}

        self._assert_matrix('post', '/api/inventory/categories/', {
            'OWNER': 201, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 201, 'ACCOUNTANT': 403,
        }, data=next_cat)

        def csv_payload():
            content = b"name,selling_price,stock_quantity\nCSVItem,50.00,10\n"
            return {'file': SimpleUploadedFile('items.csv', content, content_type='text/csv')}

        self._assert_matrix('post', '/api/inventory/products/upload-csv/', {
            'OWNER': 200, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 200, 'ACCOUNTANT': 403,
        }, data=csv_payload, fmt='multipart')

        self._assert_matrix('post', '/api/sales/invoices/', {
            'OWNER': 201, 'MANAGER': 201, 'CASHIER': 201, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data=lambda: {'payment_method': 'CASH', 'items': [{'product_id': self.product.id, 'quantity': '1.000'}]})
        self._assert_matrix('get', '/api/sales/invoices/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 200, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 200,
        })
        self._assert_matrix('post', f'/api/sales/invoices/{self.invoice.public_id}/void/', {
            'OWNER': 400, 'MANAGER': 400, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data={})
        self._assert_matrix('post', f'/api/sales/invoices/{self.invoice.public_id}/return/', {
            'OWNER': 400, 'MANAGER': 400, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data={})

        self._assert_matrix('get', '/api/sales/customers/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 200, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 200,
        })
        self._assert_matrix('post', '/api/sales/customers/', {
            'OWNER': 201, 'MANAGER': 201, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data=lambda: {'name': 'New Cust', 'phone': '0770000000'})
        self._assert_matrix('get', '/api/sales/credit-payments/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 200,
        })
        self._assert_matrix('post', '/api/sales/credit-payments/', {
            'OWNER': 400, 'MANAGER': 400, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data={})
        self._assert_matrix('get', '/api/sales/pd-cheques/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 200,
        })
        self._assert_matrix('post', '/api/sales/pd-cheques/', {
            'OWNER': 400, 'MANAGER': 400, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data={})

        self._assert_matrix('get', '/api/sales/dashboard/', {
            'OWNER': 200, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        })
        self._assert_matrix('get', '/api/staff/', {
            'OWNER': 200, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        })
        self._assert_matrix('get', '/api/core/shop-settings/', {
            'OWNER': 200, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        })
        self._assert_matrix('patch', '/api/core/shop-settings/', {
            'OWNER': 200, 'MANAGER': 403, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 403,
        }, data={'cashier_max_discount_pct': '10.00'})
        self._assert_matrix('get', '/api/core/audit-logs/', {
            'OWNER': 200, 'MANAGER': 200, 'CASHIER': 403, 'INVENTORY_MANAGER': 403, 'ACCOUNTANT': 200,
        })

    def test_owner_shop_settings_toggles_dynamically_affect_manager(self):
        """
        PATCH /api/core/shop-settings/ updates toggles, logs SHOP_SETTINGS_UPDATED, and
        immediately grants/revokes MANAGER permissions on the very next request.
        """
        self.client.force_authenticate(user=self.owner)
        patch_res = self.client.patch(
            '/api/core/shop-settings/',
            data={
                'managers_can_edit_products': True,
                'managers_can_view_cost_price': True,
                'managers_can_view_profit': True,
                'managers_can_manage_cashiers': True,
            },
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AuditLog.objects.filter(
                action='SHOP_SETTINGS_UPDATED',
                shop=self.shop,
                actor=self.owner,
            ).exists()
        )

        # MANAGER immediately gains all 4 capabilities
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(
            self.client.post(
                '/api/inventory/products/',
                data={'name': 'Mgr Created', 'selling_price': '50.00'},
                format='json',
            ).status_code,
            status.HTTP_201_CREATED,
        )
        prod_list = self.client.get('/api/inventory/products/')
        self.assertIn('cost_price', prod_list.data[0])
        dash_res = self.client.get('/api/dashboard/summary/')
        self.assertIn('profit', dash_res.data)
        self.assertEqual(self.client.get('/api/staff/').status_code, status.HTTP_200_OK)

        # Toggle back to False -> MANAGER immediately loses them
        self.client.force_authenticate(user=self.owner)
        self.client.patch(
            '/api/core/shop-settings/',
            data={
                'managers_can_edit_products': False,
                'managers_can_view_cost_price': False,
                'managers_can_view_profit': False,
                'managers_can_manage_cashiers': False,
            },
            format='json',
        )
        self.client.force_authenticate(user=self.manager)
        self.assertEqual(
            self.client.post(
                '/api/inventory/products/',
                data={'name': 'Mgr Blocked', 'selling_price': '50.00'},
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertNotIn('cost_price', self.client.get('/api/inventory/products/').data[0])
        self.assertNotIn('profit', self.client.get('/api/dashboard/summary/').data)
        self.assertEqual(self.client.get('/api/staff/').status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_summary_per_role_and_credit_flag(self):
        """
        GET /api/dashboard/summary/ returns only permitted sections; forbidden keys are absent;
        credit/cheque sub-fields are omitted when enable_credit_module=False.
        """
        expected_sections = {
            self.owner: {'operational', 'profit', 'cashier', 'inventory', 'finance'},
            self.manager: {'operational'},
            self.cashier: {'cashier'},
            self.inv_mgr: {'inventory'},
            self.accountant: {'profit', 'finance'},
        }
        all_sections = {'operational', 'profit', 'cashier', 'inventory', 'finance'}

        for user, expected_keys in expected_sections.items():
            self.client.force_authenticate(user=user)
            res = self.client.get('/api/dashboard/summary/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(set(res.data.keys()), expected_keys)
            for forbidden_key in all_sections - expected_keys:
                self.assertNotIn(forbidden_key, res.data)

        # Disable credit module -> finance section omits credit/cheque sub-fields
        self.shop.enable_credit_module = False
        self.shop.save()
        self.client.force_authenticate(user=self.accountant)
        fin_res = self.client.get('/api/dashboard/summary/')
        self.assertEqual(fin_res.status_code, status.HTTP_200_OK)
        self.assertIn('finance', fin_res.data)
        self.assertNotIn('today_credit_issued', fin_res.data['finance'])
        self.assertNotIn('outstanding_credit_total', fin_res.data['finance'])
        self.assertNotIn('upcoming_cheques_7d_count', fin_res.data['finance'])

    def test_all_active_permissions_are_enforced_somewhere(self):
        """
        Registry Enforcement Test:
        Every permission in PERMISSIONS must either be in RESERVED_PERMISSIONS or be
        actively enforced by at least one ViewSet, APIView, or Serializer.
        """
        self.assertEqual(set(PERMISSIONS.keys()), set(ACTIVE_PERMISSIONS) | set(RESERVED_PERMISSIONS))

        enforced = set()

        def walk_urls(urlpatterns):
            for pattern in urlpatterns:
                if isinstance(pattern, URLResolver):
                    walk_urls(pattern.url_patterns)
                elif isinstance(pattern, URLPattern):
                    cb = pattern.callback
                    view_cls = getattr(cb, 'cls', None) or getattr(cb, 'view_class', None)
                    if not view_cls:
                        continue
                    action_map = getattr(view_cls, 'action_permissions', None)
                    if action_map:
                        for spec in action_map.values():
                            if isinstance(spec, str):
                                enforced.add(spec)
                            else:
                                enforced.update(spec)
                    req_perm = getattr(view_cls, 'required_permission', None)
                    if req_perm:
                        if isinstance(req_perm, str):
                            enforced.add(req_perm)
                        else:
                            enforced.update(req_perm)

        walk_urls(get_resolver().url_patterns)

        # Also inspect serializer/view sources for inline permission checks (field/section/queryset)
        inline_sources = '\n'.join([
            inspect.getsource(core_views),
            inspect.getsource(inv_serializers),
            inspect.getsource(sales_serializers),
            inspect.getsource(sales_views),
        ])
        for perm in ACTIVE_PERMISSIONS:
            if f"'{perm}'" in inline_sources or f'"{perm}"' in inline_sources:
                enforced.add(perm)

        unenforced = ACTIVE_PERMISSIONS - enforced
        self.assertEqual(
            unenforced,
            set(),
            f"Active permissions defined in RBAC registry are not enforced anywhere: {unenforced}",
        )
