from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Shop, User
from inventory.models import Product, StockMovement
from sales.models import (
    Customer,
    Invoice,
    InvoiceItem,
    SalesReturn,
    SalesReturnItem,
)


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
        product_names = [p['name'] for p in response.data['results']]
        self.assertIn("Alpha Tea", product_names)
        self.assertNotIn("Beta Coffee", product_names)

    def test_shop_a_cannot_see_shop_b_invoices(self):
        """Shop A cannot list or retrieve individual invoices belonging to Shop B."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List invoices
        list_response = self.client.get('/api/sales/invoices/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        invoice_numbers = [inv['invoice_number'] for inv in list_response.data['results']]
        self.assertIn("INV-A-0001", invoice_numbers)
        self.assertNotIn("INV-B-0001", invoice_numbers)

        # 2. Direct IDOR attempt: Retrieve Shop B's invoice by public_id
        detail_response = self.client.get(f'/api/sales/invoices/{self.invoice_b.public_id}/')
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


class DecimalCheckoutAndStockLedgerTests(APITestCase):
    """
    Tests for Decimal-precision POS checkout and immutable StockMovement ledger.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="Ledger Mart", enable_credit_module=True)
        self.cashier = User.objects.create_user(
            username="ledger_cashier",
            password="password123",
            shop=self.shop,
            role=User.Role.CASHIER
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Sugar Bulk",
            cost_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            stock_quantity=Decimal('10.000'),
            reorder_level=Decimal('2.000')
        )

    def test_fractional_quantity_checkout_and_stock_ledger_entry(self):
        """Checkout with fractional decimal quantity records accurate stock deduction and StockMovement."""
        self.client.force_authenticate(user=self.cashier)

        payload = {
            "payment_method": "CASH",
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": "1.250"
                }
            ]
        }

        response = self.client.post('/api/sales/invoices/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 10.000 - 1.250 = 8.750
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('8.750'))

        # Line total = 1.250 * 150.00 = 187.50
        invoice_item = InvoiceItem.objects.get(invoice_id=response.data['id'])
        self.assertEqual(invoice_item.quantity, Decimal('1.250'))
        self.assertEqual(invoice_item.line_total, Decimal('187.50'))

        # Verify StockMovement ledger
        movement = StockMovement.objects.filter(
            product=self.product,
            movement_type=StockMovement.MovementType.SALE
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_change, Decimal('-1.250'))
        self.assertEqual(movement.balance_after, Decimal('8.750'))
        self.assertEqual(movement.reference_type, 'Invoice')
        self.assertEqual(movement.performed_by, self.cashier)

    def test_stock_movement_immutability_enforced(self):
        """StockMovement ledger entries cannot be modified or deleted via ORM or bulk operations."""
        movement = StockMovement.objects.create(
            shop=self.shop,
            product=self.product,
            movement_type=StockMovement.MovementType.INITIAL_STOCK,
            quantity_change=Decimal('10.000'),
            balance_after=Decimal('10.000'),
            performed_by=self.cashier
        )

        # Individual save update raises RuntimeError
        movement.notes = "Tampered notes"
        with self.assertRaises(RuntimeError):
            movement.save()

        # Individual delete raises RuntimeError
        with self.assertRaises(RuntimeError):
            movement.delete()

        # Bulk update raises RuntimeError
        with self.assertRaises(RuntimeError):
            StockMovement.objects.filter(id=movement.id).update(notes="Bulk tampered")

        # Bulk delete raises RuntimeError
        with self.assertRaises(RuntimeError):
            StockMovement.objects.filter(id=movement.id).delete()


class InvoiceIdempotencyTests(APITestCase):
    """
    Tests for checkout idempotency using Idempotency-Key request headers.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="Idempotency Mart", enable_credit_module=True)
        self.cashier = User.objects.create_user(
            username="idem_cashier",
            password="password123",
            shop=self.shop,
            role=User.Role.CASHIER
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Wheat Flour",
            cost_price=Decimal('80.00'),
            selling_price=Decimal('120.00'),
            stock_quantity=Decimal('20.000')
        )

    def test_idempotency_key_prevents_duplicate_checkout(self):
        """Replaying a checkout request with the same Idempotency-Key returns existing invoice without re-deducting."""
        self.client.force_authenticate(user=self.cashier)

        payload = {
            "payment_method": "CASH",
            "items": [{"product_id": self.product.id, "quantity": "2.000"}]
        }
        headers = {"HTTP_IDEMPOTENCY_KEY": "pos-retry-uuid-abc-123"}

        # First checkout: creates invoice and deducts stock
        first_res = self.client.post('/api/sales/invoices/', data=payload, format='json', **headers)
        self.assertEqual(first_res.status_code, status.HTTP_201_CREATED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('18.000'))
        self.assertEqual(Invoice.objects.filter(shop=self.shop).count(), 1)

        # Second checkout (simulating network timeout / retry): returns 200 OK with original invoice
        second_res = self.client.post('/api/sales/invoices/', data=payload, format='json', **headers)
        self.assertEqual(second_res.status_code, status.HTTP_200_OK)
        self.assertEqual(second_res.data['public_id'], first_res.data['public_id'])
        self.assertEqual(second_res.data['invoice_number'], first_res.data['invoice_number'])

        # Stock must remain 18.000, NOT deducted twice!
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('18.000'))
        self.assertEqual(Invoice.objects.filter(shop=self.shop).count(), 1)


class InvoiceImmutabilityAndDeleteProtectionTests(APITestCase):
    """
    Tests ensuring invoices cannot be deleted through API or ORM.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="Audit Mart", enable_credit_module=True)
        self.owner = User.objects.create_user(
            username="audit_owner",
            password="password123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Tea Box",
            cost_price=Decimal('50.00'),
            selling_price=Decimal('100.00'),
            stock_quantity=Decimal('50.000')
        )
        self.invoice = Invoice.objects.create(
            shop=self.shop,
            invoice_number="INV-AUDIT-0001",
            cashier=self.owner,
            subtotal=Decimal('100.00'),
            total_amount=Decimal('100.00'),
            amount_paid=Decimal('100.00')
        )

    def test_api_delete_invoice_returns_405_method_not_allowed(self):
        """HTTP DELETE on invoice detail endpoint must be rejected with 405 Method Not Allowed."""
        self.client.force_authenticate(user=self.owner)
        res = self.client.delete(f'/api/sales/invoices/{self.invoice.public_id}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Invoice.objects.filter(id=self.invoice.id).exists())

    def test_orm_delete_invoice_raises_value_error(self):
        """Calling .delete() on an Invoice instance must raise ValueError."""
        with self.assertRaises(ValueError):
            self.invoice.delete()


class InvoiceVoidWorkflowTests(APITestCase):
    """
    Tests for invoice voiding, stock restoration, and credit reversal.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="Void Mart", enable_credit_module=True)
        self.owner = User.objects.create_user(
            username="void_owner",
            password="password123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.cashier = User.objects.create_user(
            username="void_cashier",
            password="password123",
            shop=self.shop,
            role=User.Role.CASHIER
        )
        self.customer = Customer.objects.create(
            shop=self.shop,
            name="Perera",
            phone="0711112222"
        )
        self.product = Product.objects.create(
            shop=self.shop,
            name="Olive Oil 1L",
            cost_price=Decimal('1200.00'),
            selling_price=Decimal('1600.00'),
            stock_quantity=Decimal('10.000')
        )

    def test_cashier_cannot_void_invoice(self):
        """Cashiers must be blocked from voiding invoices (403 Forbidden)."""
        self.client.force_authenticate(user=self.cashier)

        # Checkout invoice
        checkout_payload = {
            "payment_method": "CASH",
            "items": [{"product_id": self.product.id, "quantity": "1.000"}]
        }
        create_res = self.client.post('/api/sales/invoices/', data=checkout_payload, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        invoice_pub_id = create_res.data['public_id']

        # Attempt void as cashier
        void_res = self.client.post(
            f'/api/sales/invoices/{invoice_pub_id}/void/',
            data={"reason": "Customer changed mind"},
            format='json'
        )
        self.assertEqual(void_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_void_restores_stock_and_reverses_credit(self):
        """Owner voiding an invoice restores inventory and reverses customer credit balance."""
        self.client.force_authenticate(user=self.owner)

        # Checkout 2 units on credit (Pay Later)
        checkout_payload = {
            "customer": self.customer.id,
            "payment_method": "CREDIT",
            "amount_paid": "0.00",
            "items": [{"product_id": self.product.id, "quantity": "2.000"}]
        }
        res = self.client.post('/api/sales/invoices/', data=checkout_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        invoice_pub_id = res.data['public_id']

        # Verify initial checkout state
        self.product.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('8.000'))
        self.assertEqual(self.customer.total_credit_balance, Decimal('3200.00'))

        # Void invoice
        void_res = self.client.post(
            f'/api/sales/invoices/{invoice_pub_id}/void/',
            data={"reason": "Customer cancelled order"},
            format='json'
        )
        self.assertEqual(void_res.status_code, status.HTTP_200_OK)
        self.assertEqual(void_res.data['status'], 'VOIDED')
        self.assertEqual(void_res.data['void_reason'], 'Customer cancelled order')

        # Stock restored: 8.000 + 2.000 = 10.000
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10.000'))

        # Credit reversed: 3200.00 - 3200.00 = 0.00
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_credit_balance, Decimal('0.00'))

        # Verify StockMovement ledger entry
        movement = StockMovement.objects.filter(
            product=self.product,
            movement_type=StockMovement.MovementType.VOID_RESTORE
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_change, Decimal('2.000'))
        self.assertEqual(movement.balance_after, Decimal('10.000'))

    def test_cannot_void_already_voided_invoice(self):
        """Attempting to void an already voided invoice returns 400 Bad Request."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            "payment_method": "CASH",
            "items": [{"product_id": self.product.id, "quantity": "1.000"}]
        }
        create_res = self.client.post('/api/sales/invoices/', data=payload, format='json')
        invoice_pub_id = create_res.data['public_id']

        # Void first time
        self.client.post(
            f'/api/sales/invoices/{invoice_pub_id}/void/',
            data={"reason": "First void"},
            format='json'
        )

        # Void second time
        res2 = self.client.post(
            f'/api/sales/invoices/{invoice_pub_id}/void/',
            data={"reason": "Second void attempt"},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already voided", res2.data['detail'])


class SalesReturnAndDashboardAccuracyTests(APITestCase):
    """
    Tests for merchandise returns, inventory restoration, credit reversal,
    and dashboard KPI net calculation accuracy.
    """
    def setUp(self):
        self.shop = Shop.objects.create(name="Return Mart", enable_credit_module=True)
        self.owner = User.objects.create_user(
            username="return_owner",
            password="password123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.cashier = User.objects.create_user(
            username="return_cashier",
            password="password123",
            shop=self.shop,
            role=User.Role.CASHIER
        )
        self.customer = Customer.objects.create(
            shop=self.shop,
            name="Silva",
            phone="0773334444"
        )
        self.product_a = Product.objects.create(
            shop=self.shop,
            name="Rice 5kg",
            cost_price=Decimal('600.00'),
            selling_price=Decimal('900.00'),
            stock_quantity=Decimal('20.000')
        )
        self.product_b = Product.objects.create(
            shop=self.shop,
            name="Dhal 1kg",
            cost_price=Decimal('200.00'),
            selling_price=Decimal('300.00'),
            stock_quantity=Decimal('30.000')
        )

    def test_partial_sales_return_workflow(self):
        """Partial return restores stock, adjusts customer credit balance, and updates status to PARTIALLY_RETURNED."""
        self.client.force_authenticate(user=self.cashier)

        # Checkout: 4x Rice on credit = Rs. 3600.00
        checkout_payload = {
            "customer": self.customer.id,
            "payment_method": "CREDIT",
            "amount_paid": "0.00",
            "items": [{"product_id": self.product_a.id, "quantity": "4.000"}]
        }
        res = self.client.post('/api/sales/invoices/', data=checkout_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        invoice_pub_id = res.data['public_id']
        invoice_item_id = res.data['items'][0]['id']

        self.product_a.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertEqual(self.product_a.stock_quantity, Decimal('16.000'))
        self.assertEqual(self.customer.total_credit_balance, Decimal('3600.00'))

        # Return 1 unit of Rice (requires sales.return_invoice: OWNER or MANAGER)
        self.client.force_authenticate(user=self.owner)
        return_payload = {
            "reason": "Bag had small tear",
            "items": [
                {
                    "invoice_item_id": invoice_item_id,
                    "quantity": "1.000"
                }
            ]
        }
        return_res = self.client.post(
            f'/api/sales/invoices/{invoice_pub_id}/return/',
            data=return_payload,
            format='json'
        )
        self.assertEqual(return_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(return_res.data['total_refund_amount']), Decimal('900.00'))
        self.assertEqual(Decimal(return_res.data['credit_reversed']), Decimal('900.00'))
        self.assertEqual(Decimal(return_res.data['cash_refunded']), Decimal('0.00'))

        # Stock restored: 16.000 + 1.000 = 17.000
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock_quantity, Decimal('17.000'))

        # Credit balance reduced: 3600.00 - 900.00 = 2700.00
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_credit_balance, Decimal('2700.00'))

        # Check invoice status is PARTIALLY_RETURNED
        inv = Invoice.objects.get(public_id=invoice_pub_id)
        self.assertEqual(inv.status, Invoice.Status.PARTIALLY_RETURNED)

        # Verify StockMovement entry
        movement = StockMovement.objects.filter(
            product=self.product_a,
            movement_type=StockMovement.MovementType.SALES_RETURN
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_change, Decimal('1.000'))
        self.assertEqual(movement.balance_after, Decimal('17.000'))

        # Verify SalesReturn and SalesReturnItem records in database
        self.assertEqual(SalesReturn.objects.filter(shop=self.shop).count(), 1)
        self.assertEqual(SalesReturnItem.objects.filter(shop=self.shop).count(), 1)

    def test_return_exceeding_purchased_quantity_is_rejected(self):
        """Attempting to return more than purchased or remaining quantity returns 400."""
        self.client.force_authenticate(user=self.cashier)

        checkout_payload = {
            "payment_method": "CASH",
            "items": [{"product_id": self.product_a.id, "quantity": "2.000"}]
        }
        res = self.client.post('/api/sales/invoices/', data=checkout_payload, format='json')
        invoice_pub_id = res.data['public_id']
        invoice_item_id = res.data['items'][0]['id']

        # Attempt to return 3 units (only 2 purchased!) as OWNER
        self.client.force_authenticate(user=self.owner)
        bad_return = {
            "reason": "Exceeding return",
            "items": [{"invoice_item_id": invoice_item_id, "quantity": "3.000"}]
        }
        return_res = self.client.post(
            f'/api/sales/invoices/{invoice_pub_id}/return/',
            data=bad_return,
            format='json'
        )
        self.assertEqual(return_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dashboard_accuracy_excludes_void_and_subtracts_returns(self):
        """Dashboard KPIs accurately exclude voided sales and subtract returned revenue and gross profit."""
        self.client.force_authenticate(user=self.owner)

        # 1. Invoice 1: 2x Product A @ 900 (cost 600) = 1800 rev, 600 profit
        inv1_payload = {
            "payment_method": "CASH",
            "items": [{"product_id": self.product_a.id, "quantity": "2.000"}]
        }
        res1 = self.client.post('/api/sales/invoices/', data=inv1_payload, format='json')
        inv1_pub_id = res1.data['public_id']
        inv1_item_id = res1.data['items'][0]['id']

        # 2. Invoice 2: 1x Product B @ 300 (cost 200) = 300 rev, 100 profit
        inv2_payload = {
            "payment_method": "CASH",
            "items": [{"product_id": self.product_b.id, "quantity": "1.000"}]
        }
        res2 = self.client.post('/api/sales/invoices/', data=inv2_payload, format='json')
        inv2_pub_id = res2.data['public_id']

        # 3. Void Invoice 2
        void_res = self.client.post(
            f'/api/sales/invoices/{inv2_pub_id}/void/',
            data={"reason": "Accidental sale"},
            format='json'
        )
        self.assertEqual(void_res.status_code, status.HTTP_200_OK)

        # 4. Return 1x Product A from Invoice 1: refund 900, returned profit 300
        return_payload = {
            "reason": "Customer returned 1 pack",
            "items": [{"invoice_item_id": inv1_item_id, "quantity": "1.000"}]
        }
        ret_res = self.client.post(
            f'/api/sales/invoices/{inv1_pub_id}/return/',
            data=return_payload,
            format='json'
        )
        self.assertEqual(ret_res.status_code, status.HTTP_201_CREATED)

        # Fetch dashboard analytics
        dash_res = self.client.get('/api/sales/dashboard/?days=1')
        self.assertEqual(dash_res.status_code, status.HTTP_200_OK)

        kpis = dash_res.data['kpis']

        # Invoice 2 is voided (excluded)
        # Invoice 1 gross = 1800, return = 900 => Net total_sales = 900.00
        self.assertEqual(Decimal(str(kpis['total_sales'])), Decimal('900.00'))

        # Invoice 1 gross profit = 600, returned profit = (900 - 600) * 1 = 300 => Net gross_profit = 300.00
        self.assertEqual(Decimal(str(kpis['gross_profit'])), Decimal('300.00'))

        # Invoice count should be 1 (Invoice 1 only, voided Invoice 2 excluded)
        self.assertEqual(kpis['invoice_count'], 1)

