from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from core.models import AuditLog, Shop, User
from inventory.models import Product
from sales.models import Invoice


class TaxAndCashierDiscountCapTests(APITestCase):
    """
    Tests for Task 4c:
    - Configurable Tax (NONE / EXCLUSIVE / INCLUSIVE) with ROUND_HALF_UP precision
    - Invoice tax snapshot immutability
    - ShopSettings tax validation & audit logging
    - Cashier discount cap enforcement vs unrestricted OWNER/MANAGER discounts
    - Dashboard summary finance.total_tax_collected
    """

    def setUp(self):
        self.shop = Shop.objects.create(
            name="Tax & Discount Mart",
            enable_credit_module=True,
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="td_owner",
            password="Password123!",
            shop=self.shop,
            role=User.Role.OWNER,
        )
        self.manager = User.objects.create_user(
            username="td_manager",
            password="Password123!",
            shop=self.shop,
            role=User.Role.MANAGER,
        )
        self.cashier = User.objects.create_user(
            username="td_cashier",
            password="Password123!",
            shop=self.shop,
            role=User.Role.CASHIER,
        )
        self.accountant = User.objects.create_user(
            username="td_accountant",
            password="Password123!",
            shop=self.shop,
            role=User.Role.ACCOUNTANT,
        )
        self.product_1000 = Product.objects.create(
            shop=self.shop,
            name="Item 1000",
            cost_price=Decimal('600.00'),
            selling_price=Decimal('1000.00'),
            stock_quantity=Decimal('50.000'),
        )
        self.product_1180 = Product.objects.create(
            shop=self.shop,
            name="Item 1180",
            cost_price=Decimal('700.00'),
            selling_price=Decimal('1180.00'),
            stock_quantity=Decimal('50.000'),
        )

    def test_shop_settings_tax_validation_and_audit_log(self):
        """INCLUSIVE/EXCLUSIVE requires positive tax_rate_pct; valid PATCH logs AuditLog."""
        self.client.force_authenticate(user=self.owner)

        bad_res = self.client.patch(
            '/api/core/shop-settings/',
            data={'tax_mode': 'EXCLUSIVE', 'tax_rate_pct': '0.00'},
            format='json',
        )
        self.assertEqual(bad_res.status_code, status.HTTP_400_BAD_REQUEST)

        good_res = self.client.patch(
            '/api/core/shop-settings/',
            data={'tax_mode': 'EXCLUSIVE', 'tax_rate_pct': '18.00', 'tax_label': 'VAT'},
            format='json',
        )
        self.assertEqual(good_res.status_code, status.HTTP_200_OK)
        self.assertEqual(good_res.data['tax_mode'], 'EXCLUSIVE')
        self.assertEqual(good_res.data['tax_rate_pct'], '18.00')
        self.assertEqual(good_res.data['tax_label'], 'VAT')

        log = AuditLog.objects.filter(
            action='SHOP_SETTINGS_UPDATED',
            shop=self.shop,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.before_state['tax_mode'], 'NONE')
        self.assertEqual(log.after_state['tax_mode'], 'EXCLUSIVE')
        self.assertEqual(log.after_state['tax_rate_pct'], '18.00')

    def test_tax_mode_none_backward_compatible(self):
        """tax_mode='NONE' produces tax_amount=0.00 and total_amount=subtotal-discount."""
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'discount': '100.00',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(res.data['tax_amount']), Decimal('0.00'))
        self.assertEqual(Decimal(res.data['total_amount']), Decimal('900.00'))
        self.assertEqual(res.data['tax_mode'], 'NONE')

    def test_tax_mode_exclusive_and_snapshot_immutability(self):
        """
        tax_mode='EXCLUSIVE' (18% VAT on Rs. 1,000.00) -> tax_amount=180.00, total_amount=1180.00.
        Changing ShopSettings.tax_rate_pct afterward does not mutate the saved invoice snapshot.
        """
        settings = self.shop.settings
        settings.tax_mode = 'EXCLUSIVE'
        settings.tax_rate_pct = Decimal('18.00')
        settings.tax_label = 'VAT'
        settings.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(res.data['subtotal']), Decimal('1000.00'))
        self.assertEqual(Decimal(res.data['tax_amount']), Decimal('180.00'))
        self.assertEqual(Decimal(res.data['total_amount']), Decimal('1180.00'))
        self.assertEqual(Decimal(res.data['amount_paid']), Decimal('1180.00'))
        self.assertEqual(res.data['tax_mode'], 'EXCLUSIVE')
        self.assertEqual(res.data['tax_rate_pct'], '18.00')

        # Change shop tax rate afterward
        settings.tax_rate_pct = Decimal('25.00')
        settings.save()

        inv = Invoice.objects.get(public_id=res.data['public_id'])
        self.assertEqual(inv.tax_rate_pct, Decimal('18.00'))
        self.assertEqual(inv.tax_amount, Decimal('180.00'))
        self.assertEqual(inv.total_amount, Decimal('1180.00'))

    def test_tax_mode_inclusive(self):
        """tax_mode='INCLUSIVE' (18% VAT on Rs. 1,180.00) -> total_amount=1180.00, tax_amount=180.00."""
        settings = self.shop.settings
        settings.tax_mode = 'INCLUSIVE'
        settings.tax_rate_pct = Decimal('18.00')
        settings.tax_label = 'VAT'
        settings.save()

        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'items': [{'product_id': self.product_1180.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(res.data['total_amount']), Decimal('1180.00'))
        self.assertEqual(Decimal(res.data['tax_amount']), Decimal('180.00'))
        self.assertEqual(res.data['tax_mode'], 'INCLUSIVE')

    def test_cashier_discount_cap_enforcement(self):
        """
        With cap 0.00%, Cashier discount > 0 returns 400.
        With cap 10.00%, Cashier can apply <= 10% and gets 400 on 10.01%.
        OWNER and MANAGER are not restricted by cashier_max_discount_pct.
        """
        # 1. Default cap 0.00%
        self.client.force_authenticate(user=self.cashier)
        res_zero = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'discount': '1.00',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.assertEqual(res_zero.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('discount', res_zero.data)

        # 2. Set cap to 10.00%
        self.shop.settings.cashier_max_discount_pct = Decimal('10.00')
        self.shop.settings.save()

        # Exactly 10% (100.00 on 1000.00) -> 201
        res_ok = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'discount': '100.00',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.assertEqual(res_ok.status_code, status.HTTP_201_CREATED)

        # 10.01% (100.10 on 1000.00) -> 400
        res_over = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'discount': '100.10',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.assertEqual(res_over.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('discount', res_over.data)

        # OWNER and MANAGER can apply > 10% (e.g. 500.00 on 1000.00)
        for actor in (self.owner, self.manager):
            self.client.force_authenticate(user=actor)
            res_staff = self.client.post(
                '/api/sales/invoices/',
                data={
                    'payment_method': 'CASH',
                    'discount': '500.00',
                    'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
                },
                format='json',
            )
            self.assertEqual(res_staff.status_code, status.HTTP_201_CREATED)

    def test_dashboard_summary_includes_total_tax_collected_for_finance_roles(self):
        """
        GET /api/dashboard/summary/ includes finance.total_tax_collected (excluding VOIDED)
        for OWNER and ACCOUNTANT, and omits finance for CASHIER.
        """
        settings = self.shop.settings
        settings.tax_mode = 'EXCLUSIVE'
        settings.tax_rate_pct = Decimal('18.00')
        settings.save()

        self.client.force_authenticate(user=self.owner)
        # Invoice 1: 180.00 tax (active)
        self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        # Invoice 2: 180.00 tax -> VOIDED (must be excluded)
        res_void_target = self.client.post(
            '/api/sales/invoices/',
            data={
                'payment_method': 'CASH',
                'items': [{'product_id': self.product_1000.id, 'quantity': '1.000'}],
            },
            format='json',
        )
        self.client.post(
            f"/api/sales/invoices/{res_void_target.data['public_id']}/void/",
            data={'reason': 'Voided sale'},
            format='json',
        )

        # OWNER & ACCOUNTANT see total_tax_collected == 180.00
        for user in (self.owner, self.accountant):
            self.client.force_authenticate(user=user)
            dash_res = self.client.get('/api/dashboard/summary/')
            self.assertEqual(dash_res.status_code, status.HTTP_200_OK)
            self.assertIn('finance', dash_res.data)
            self.assertEqual(
                Decimal(str(dash_res.data['finance']['total_tax_collected'])),
                Decimal('180.00'),
            )

        # CASHIER does not see finance section
        self.client.force_authenticate(user=self.cashier)
        cashier_dash = self.client.get('/api/dashboard/summary/')
        self.assertEqual(cashier_dash.status_code, status.HTTP_200_OK)
        self.assertNotIn('finance', cashier_dash.data)
