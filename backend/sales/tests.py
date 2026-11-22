from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Shop, User
from inventory.models import Product
from sales.models import Customer, Invoice, InvoiceItem


class MultiTenantDataIsolationTests(APITestCase):
    """
    Test suite for Multi-Tenant Data Isolation (Rule 1 of ARCHITECTURE.md).
    Ensures that Shop Alpha cannot view, modify, or leak data from Shop Beta.
    """
    def setUp(self):
        # Tenant A
        self.shop_a = Shop.objects.create(name="Shop Alpha", enable_credit_module=True)
        self.owner_a = User.objects.create_user(
            username="owner_a",
            password="password123",
            shop=self.shop_a,
            role=User.Role.OWNER
        )
        self.product_a = Product.objects.create(
            shop=self.shop_a,
            name="Alpha Tea",
            cost_price=Decimal('50.00'),
            selling_price=Decimal('80.00'),
            stock_quantity=100
        )
        self.invoice_a = Invoice.objects.create(
            shop=self.shop_a,
            invoice_number="INV-A-0001",
            cashier=self.owner_a,
            subtotal=Decimal('80.00'),
            total_amount=Decimal('80.00'),
            amount_paid=Decimal('80.00')
        )

        # Tenant B
        self.shop_b = Shop.objects.create(name="Shop Beta", enable_credit_module=True)
        self.owner_b = User.objects.create_user(
            username="owner_b",
            password="password123",
            shop=self.shop_b,
            role=User.Role.OWNER
        )
        self.product_b = Product.objects.create(
            shop=self.shop_b,
            name="Beta Coffee",
            cost_price=Decimal('120.00'),
            selling_price=Decimal('180.00'),
            stock_quantity=50
        )
        self.invoice_b = Invoice.objects.create(
            shop=self.shop_b,
            invoice_number="INV-B-0001",
            cashier=self.owner_b,
            subtotal=Decimal('180.00'),
            total_amount=Decimal('180.00'),
            amount_paid=Decimal('180.00')
        )

    def test_shop_a_cannot_see_shop_b_products(self):
        """Shop A's product list must only contain its own inventory."""
        self.client.force_authenticate(user=self.owner_a)
        response = self.client.get('/api/inventory/products/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product_names = [p['name'] for p in response.data]
        self.assertIn("Alpha Tea", product_names)
        self.assertNotIn("Beta Coffee", product_names)

    def test_shop_a_cannot_see_shop_b_invoices(self):
        """Shop A cannot list or retrieve individual invoices belonging to Shop B."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List invoices
        list_response = self.client.get('/api/sales/invoices/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        invoice_numbers = [inv['invoice_number'] for inv in list_response.data]
        self.assertIn("INV-A-0001", invoice_numbers)
        self.assertNotIn("INV-B-0001", invoice_numbers)

        # 2. Direct IDOR attempt: Retrieve Shop B's invoice ID
        detail_response = self.client.get(f'/api/sales/invoices/{self.invoice_b.id}/')
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)


class POSCheckoutAndStockDeductionTests(APITestCase):
    """
    Test suite for Atomic POS Checkout and Concurrency Safety.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="City Mart", enable_credit_module=True)
        self.cashier = User.objects.create_user(
            username="cashier_jane",
            password="password123",
            shop=self.shop,
            role=User.Role.CASHIER
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Anchor Milk 400g",
            cost_price=Decimal('800.00'),
            selling_price=Decimal('1050.00'),
            stock_quantity=10,
            reorder_level=3
        )

    def test_successful_checkout_deducts_stock_and_snapshots_cost(self):
        """Checkout must atomically deduct stock and record wholesale cost snapshot."""
        self.client.force_authenticate(user=self.cashier)

        payload = {
            "payment_method": "CASH",
            "amount_paid": "2100.00",
            "discount": "0.00",
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": 2
                }
            ]
        }

        response = self.client.post('/api/sales/invoices/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify stock was deducted: 10 - 2 = 8
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

        # Verify cost price snapshot on line item
        invoice_item = InvoiceItem.objects.get(invoice_id=response.data['id'])
        self.assertEqual(invoice_item.cost_price_at_sale, Decimal('800.00'))
        self.assertEqual(invoice_item.unit_price, Decimal('1050.00'))
        self.assertEqual(invoice_item.line_total, Decimal('2100.00'))

    def test_insufficient_stock_fails_and_rolls_back(self):
        """Attempting to buy more than available stock must return 400 and preserve stock."""
        self.client.force_authenticate(user=self.cashier)

        payload = {
            "payment_method": "CASH",
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": 15  # Only 10 available!
                }
            ]
        }

        response = self.client.post('/api/sales/invoices/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient stock", str(response.data))

        # Stock must remain unchanged at 10
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)


class FeatureFlagCreditModuleTests(APITestCase):
    """
    Test suite for SaaS Modularity & Feature Flags (Rule 2 of ARCHITECTURE.md).
    """
    def setUp(self):
        # Shop with Credit Module DISABLED
        self.shop = Shop.objects.create(name="Basic Kiosk", enable_credit_module=False)
        self.owner = User.objects.create_user(
            username="kiosk_owner",
            password="password123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Biscuits",
            selling_price=Decimal('100.00'),
            stock_quantity=20
        )
        self.customer = Customer.objects.create(
            shop=self.shop,
            name="Kamal",
            phone="0779998888"
        )

    def test_disabled_credit_module_blocks_credit_checkout(self):
        """Shops without credit module subscription cannot sell items on credit."""
        self.client.force_authenticate(user=self.owner)

        payload = {
            "customer": self.customer.id,
            "payment_method": "CREDIT",
            "amount_paid": "0.00",
            "items": [{"product_id": self.product.id, "quantity": 1}]
        }

        response = self.client.post('/api/sales/invoices/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Credit sales are disabled", str(response.data))

    def test_disabled_credit_module_blocks_credit_endpoints(self):
        """Endpoints for customer credit ledger & PD cheques must return 403 Forbidden."""
        self.client.force_authenticate(user=self.owner)

        # 1. Customer Credit Ledger
        customer_res = self.client.get('/api/sales/customers/')
        self.assertEqual(customer_res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. PD Cheques
        cheque_res = self.client.get('/api/sales/pd-cheques/')
        self.assertEqual(cheque_res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Credit Settlements
        payment_res = self.client.get('/api/sales/credit-payments/')
        self.assertEqual(payment_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_enabling_feature_flag_unlocks_endpoints(self):
        """Subscribing to the Credit Module dynamically unlocks all credit endpoints."""
        self.shop.enable_credit_module = True
        self.shop.save()

        self.client.force_authenticate(user=self.owner)
        customer_res = self.client.get('/api/sales/customers/')
        self.assertEqual(customer_res.status_code, status.HTTP_200_OK)


class DashboardAnalyticsPermissionTests(APITestCase):
    """
    Test suite for Owner Dashboard Analytics permissions.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="Analytics Shop", enable_credit_module=True)
        self.owner = User.objects.create_user(
            username="shop_owner",
            password="password123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.cashier = User.objects.create_user(
            username="shop_cashier",
            password="password123",
            shop=self.shop,
            role=User.Role.CASHIER
        )

    def test_cashier_forbidden_from_dashboard(self):
        """Cashiers must receive 403 Forbidden on the business analytics endpoint."""
        self.client.force_authenticate(user=self.cashier)
        response = self.client.get('/api/sales/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_access_dashboard_analytics(self):
        """Shop Owner receives 200 OK with aggregated financial KPIs."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/sales/dashboard/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("kpis", response.data)
        self.assertIn("total_sales", response.data['kpis'])
        self.assertIn("gross_profit", response.data['kpis'])
        self.assertIn("low_stock_count", response.data['kpis'])
        self.assertIn("top_selling_products", response.data)
