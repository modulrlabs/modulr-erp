import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Shop, User
from inventory.models import Category, Product
from sales.models import CreditPayment, Customer, Invoice, PDCheque


class SystematicTenantIsolationSecurityTests(APITestCase):
    """
    Comprehensive Cross-Tenant Isolation and Security Test Suite (Phase 1A — Task 2a).

    WHY THIS TEST SUITE IS CRITICAL:
    In a B2B Multi-tenant SaaS, cross-tenant data leakage or Insecure Direct Object
    Reference (IDOR) vulnerabilities represent existential security risks.
    This suite rigorously verifies that:
    1. Tenant A cannot list, retrieve, update, or delete Tenant B's data across all entities.
    2. POS Barcode scanning for Tenant B's barcode returns 404 for Tenant A.
    3. FK spoofing / IDOR injection during creation/checkout is rejected with 400 Bad Request
       without leaking whether the foreign key ID exists in another tenant.
    4. Business state (stock quantity, customer credit balance) in Tenant B is never mutated
       by unauthorized cross-tenant operations from Tenant A.
    5. Inactive shop subscriptions receive 403 PermissionDenied across all business endpoints.
    """

    def setUp(self):
        cache.clear()
        today = timezone.now().date()

        # ----------------------------------------------------------------------
        # Tenant A Setup (Shop Alpha)
        # ----------------------------------------------------------------------
        self.shop_a = Shop.objects.create(
            name="Shop Alpha",
            enable_credit_module=True,
            is_active=True
        )
        self.owner_a = User.objects.create_user(
            username="owner_alpha",
            password="password123",
            shop=self.shop_a,
            role=User.Role.OWNER
        )
        self.cashier_a = User.objects.create_user(
            username="cashier_alpha",
            password="password123",
            shop=self.shop_a,
            role=User.Role.CASHIER
        )
        self.category_a = Category.objects.create(
            shop=self.shop_a,
            name="Alpha Beverages"
        )
        self.product_a = Product.objects.create(
            shop=self.shop_a,
            category=self.category_a,
            name="Alpha Ceylon Tea",
            barcode="111111",
            cost_price=Decimal("50.00"),
            selling_price=Decimal("100.00"),
            stock_quantity=50
        )
        self.customer_a = Customer.objects.create(
            shop=self.shop_a,
            name="Alice Alpha",
            phone="0711111111",
            total_credit_balance=Decimal("0.00")
        )
        self.invoice_a = Invoice.objects.create(
            shop=self.shop_a,
            invoice_number="INV-A-0001",
            customer=self.customer_a,
            cashier=self.owner_a,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("100.00")
        )
        self.credit_payment_a = CreditPayment.objects.create(
            shop=self.shop_a,
            customer=self.customer_a,
            amount_paid=Decimal("50.00"),
            received_by=self.owner_a
        )
        self.pd_cheque_a = PDCheque.objects.create(
            shop=self.shop_a,
            customer=self.customer_a,
            cheque_number="CHQ-A-001",
            bank_name="Bank of Ceylon",
            amount=Decimal("500.00"),
            due_date=today + timedelta(days=3)
        )

        # ----------------------------------------------------------------------
        # Tenant B Setup (Shop Beta)
        # ----------------------------------------------------------------------
        self.shop_b = Shop.objects.create(
            name="Shop Beta",
            enable_credit_module=True,
            is_active=True
        )
        self.owner_b = User.objects.create_user(
            username="owner_beta",
            password="password123",
            shop=self.shop_b,
            role=User.Role.OWNER
        )
        self.cashier_b = User.objects.create_user(
            username="cashier_beta",
            password="password123",
            shop=self.shop_b,
            role=User.Role.CASHIER
        )
        self.category_b = Category.objects.create(
            shop=self.shop_b,
            name="Beta Snacks"
        )
        self.product_b = Product.objects.create(
            shop=self.shop_b,
            category=self.category_b,
            name="Beta Crisps",
            barcode="222222",
            cost_price=Decimal("70.00"),
            selling_price=Decimal("120.00"),
            stock_quantity=30
        )
        self.customer_b = Customer.objects.create(
            shop=self.shop_b,
            name="Bob Beta",
            phone="0722222222",
            total_credit_balance=Decimal("200.00")
        )
        self.invoice_b = Invoice.objects.create(
            shop=self.shop_b,
            invoice_number="INV-B-0001",
            customer=self.customer_b,
            cashier=self.owner_b,
            subtotal=Decimal("120.00"),
            total_amount=Decimal("120.00"),
            amount_paid=Decimal("120.00")
        )
        self.credit_payment_b = CreditPayment.objects.create(
            shop=self.shop_b,
            customer=self.customer_b,
            amount_paid=Decimal("100.00"),
            received_by=self.owner_b
        )
        self.pd_cheque_b = PDCheque.objects.create(
            shop=self.shop_b,
            customer=self.customer_b,
            cheque_number="CHQ-B-001",
            bank_name="Sampath Bank",
            amount=Decimal("1000.00"),
            due_date=today + timedelta(days=5)
        )

        # ----------------------------------------------------------------------
        # Inactive Tenant Setup
        # ----------------------------------------------------------------------
        self.shop_inactive = Shop.objects.create(
            name="Shop Inactive",
            enable_credit_module=True,
            is_active=False
        )
        self.user_inactive = User.objects.create_user(
            username="user_inactive",
            password="password123",
            shop=self.shop_inactive,
            role=User.Role.OWNER
        )

    # ==========================================================================
    # 1. READ / UPDATE / DELETE ISOLATION TESTS
    # ==========================================================================

    def test_owner_a_cannot_access_or_mutate_shop_b_categories(self):
        """Owner A cannot list, retrieve (404), update (404), or delete (404) Shop B's category."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List: Category B must not appear in Shop A's category list
        res = self.client.get("/api/inventory/categories/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        cat_ids = [c["id"] for c in res.data]
        self.assertIn(self.category_a.id, cat_ids)
        self.assertNotIn(self.category_b.id, cat_ids)

        # 2. Retrieve: GET /{public_id}/ on Shop B category must return 404
        res = self.client.get(f"/api/inventory/categories/{self.category_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Update: PATCH /{public_id}/ must return 404 and leave Category B unmodified
        res = self.client.patch(
            f"/api/inventory/categories/{self.category_b.public_id}/",
            data={"name": "Hacked Category"}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.category_b.refresh_from_db()
        self.assertEqual(self.category_b.name, "Beta Snacks")

        # 4. Delete: DELETE /{public_id}/ must return 404 and keep Category B in database
        res = self.client.delete(f"/api/inventory/categories/{self.category_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Category.objects.filter(id=self.category_b.id).exists())

    def test_owner_a_cannot_access_or_mutate_shop_b_products(self):
        """Owner A cannot list, retrieve (404), update (404), or delete (404) Shop B's product."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List
        res = self.client.get("/api/inventory/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        prod_ids = [p["id"] for p in res.data]
        self.assertIn(self.product_a.id, prod_ids)
        self.assertNotIn(self.product_b.id, prod_ids)

        # 2. Retrieve
        res = self.client.get(f"/api/inventory/products/{self.product_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Update
        res = self.client.patch(
            f"/api/inventory/products/{self.product_b.public_id}/",
            data={"selling_price": "1.00"}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.selling_price, Decimal("120.00"))

        # 4. Delete
        res = self.client.delete(f"/api/inventory/products/{self.product_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Product.objects.filter(id=self.product_b.id).exists())

    def test_owner_a_cannot_access_or_mutate_shop_b_customers(self):
        """Owner A cannot list, retrieve (404), update (404), or delete (404) Shop B's customer."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List
        res = self.client.get("/api/sales/customers/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        cust_ids = [c["id"] for c in res.data]
        self.assertIn(self.customer_a.id, cust_ids)
        self.assertNotIn(self.customer_b.id, cust_ids)

        # 2. Retrieve
        res = self.client.get(f"/api/sales/customers/{self.customer_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Update
        res = self.client.patch(
            f"/api/sales/customers/{self.customer_b.public_id}/",
            data={"name": "Hacked Customer"}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.customer_b.refresh_from_db()
        self.assertEqual(self.customer_b.name, "Bob Beta")

        # 4. Delete
        res = self.client.delete(f"/api/sales/customers/{self.customer_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Customer.objects.filter(id=self.customer_b.id).exists())

    def test_owner_a_cannot_access_or_mutate_shop_b_invoices(self):
        """Owner A cannot list or retrieve (404) Shop B's invoices."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List
        res = self.client.get("/api/sales/invoices/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        inv_ids = [inv["id"] for inv in res.data]
        self.assertIn(self.invoice_a.id, inv_ids)
        self.assertNotIn(self.invoice_b.id, inv_ids)

        # 2. Retrieve
        res = self.client.get(f"/api/sales/invoices/{self.invoice_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_a_cannot_access_or_mutate_shop_b_credit_payments(self):
        """Owner A cannot list, retrieve (404), update (404), or delete (404) Shop B's credit settlements."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List
        res = self.client.get("/api/sales/credit-payments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        payment_ids = [cp["id"] for cp in res.data]
        self.assertIn(self.credit_payment_a.id, payment_ids)
        self.assertNotIn(self.credit_payment_b.id, payment_ids)

        # 2. Retrieve
        res = self.client.get(f"/api/sales/credit-payments/{self.credit_payment_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Update
        res = self.client.patch(
            f"/api/sales/credit-payments/{self.credit_payment_b.public_id}/",
            data={"notes": "Tampered note"}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Delete
        res = self.client.delete(f"/api/sales/credit-payments/{self.credit_payment_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CreditPayment.objects.filter(id=self.credit_payment_b.id).exists())

    def test_owner_a_cannot_access_or_mutate_shop_b_pd_cheques(self):
        """Owner A cannot list, retrieve (404), update (404), or delete (404) Shop B's PD cheques."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List
        res = self.client.get("/api/sales/pd-cheques/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        chq_ids = [c["id"] for c in res.data]
        self.assertIn(self.pd_cheque_a.id, chq_ids)
        self.assertNotIn(self.pd_cheque_b.id, chq_ids)

        # 2. Retrieve
        res = self.client.get(f"/api/sales/pd-cheques/{self.pd_cheque_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Update
        res = self.client.patch(
            f"/api/sales/pd-cheques/{self.pd_cheque_b.public_id}/",
            data={"bank_name": "Tampered Bank"}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.pd_cheque_b.refresh_from_db()
        self.assertEqual(self.pd_cheque_b.bank_name, "Sampath Bank")

        # 4. Delete
        res = self.client.delete(f"/api/sales/pd-cheques/{self.pd_cheque_b.public_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(PDCheque.objects.filter(id=self.pd_cheque_b.id).exists())

    # ==========================================================================
    # 2. BARCODE LOOKUP ISOLATION TEST
    # ==========================================================================

    def test_barcode_lookup_cross_tenant_isolation(self):
        """
        Querying ?code=<barcode> for an existing barcode in Shop B must return 404 for Shop A.
        Prevents cross-tenant barcode probing or leaking competitor catalog pricing.
        """
        self.client.force_authenticate(user=self.owner_a)

        # Shop B has product with barcode '222222'
        res = self.client.get(f"/api/inventory/products/by-barcode/?code={self.product_b.barcode}")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("not found in your inventory", res.data["detail"])

    # ==========================================================================
    # 3. FOREIGN KEY INJECTION / IDOR TESTS
    # ==========================================================================

    def test_cross_tenant_fk_injection_product_creation(self):
        """
        Owner A attempting to create a product referencing Shop B's category ID
        must be rejected with 400 Bad Request and a generic error message.
        """
        self.client.force_authenticate(user=self.owner_a)

        payload = {
            "name": "Malicious Product",
            "category": self.category_b.id,
            "barcode": "333333",
            "cost_price": "40.00",
            "selling_price": "80.00",
            "stock_quantity": 10
        }

        res = self.client.post("/api/inventory/products/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", res.data)
        self.assertIn("Invalid category selection.", str(res.data["category"]))

        # Ensure product was NOT created in DB
        self.assertFalse(Product.objects.filter(barcode="333333").exists())

    def test_cross_tenant_fk_injection_invoice_checkout_customer(self):
        """
        Checkout in Shop A referencing Shop B's customer ID must be rejected with 400.
        Shop B customer credit balance must NOT be altered.
        """
        self.client.force_authenticate(user=self.owner_a)

        payload = {
            "customer": self.customer_b.id,
            "payment_method": "CREDIT",
            "amount_paid": "0.00",
            "items": [
                {
                    "product_id": self.product_a.id,
                    "quantity": 1
                }
            ]
        }

        res = self.client.post("/api/sales/invoices/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("customer", res.data)
        self.assertIn("Invalid customer selection.", str(res.data["customer"]))

        # Shop B's customer credit balance must remain intact
        self.customer_b.refresh_from_db()
        self.assertEqual(self.customer_b.total_credit_balance, Decimal("200.00"))

    def test_cross_tenant_fk_injection_invoice_checkout_product(self):
        """
        Checkout in Shop A referencing Shop B's product ID must be rejected with 400.
        Shop B's stock quantity must NOT be decremented.
        """
        self.client.force_authenticate(user=self.owner_a)

        payload = {
            "payment_method": "CASH",
            "amount_paid": "120.00",
            "items": [
                {
                    "product_id": self.product_b.id,  # Belongs to Shop B!
                    "quantity": 5
                }
            ]
        }

        res = self.client.post("/api/sales/invoices/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("items", res.data)
        self.assertIn("One or more products are invalid or unavailable.", str(res.data["items"]))

        # Shop B's product stock must remain exactly 30 (not 25)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.stock_quantity, 30)

    def test_cross_tenant_fk_injection_credit_payment(self):
        """
        Settling credit in Shop A against Shop B's customer must be rejected with 400.
        Shop B's customer credit balance must NOT change.
        """
        self.client.force_authenticate(user=self.owner_a)

        payload = {
            "customer": self.customer_b.id,  # Belongs to Shop B!
            "amount_paid": "50.00",
            "payment_method": "CASH"
        }

        res = self.client.post("/api/sales/credit-payments/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("customer", res.data)
        self.assertIn("Invalid customer selection.", str(res.data["customer"]))

        # Verify Shop B customer balance remains unchanged
        self.customer_b.refresh_from_db()
        self.assertEqual(self.customer_b.total_credit_balance, Decimal("200.00"))

    def test_cross_tenant_fk_injection_pd_cheque(self):
        """
        Recording a PD Cheque in Shop A referencing Shop B's customer must be rejected with 400.
        """
        self.client.force_authenticate(user=self.owner_a)

        payload = {
            "customer": self.customer_b.id,  # Belongs to Shop B!
            "cheque_number": "CHQ-ATTACK-01",
            "bank_name": "Commercial Bank",
            "amount": "2500.00",
            "due_date": str(timezone.now().date() + timedelta(days=10))
        }

        res = self.client.post("/api/sales/pd-cheques/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("customer", res.data)
        self.assertIn("Invalid customer selection.", str(res.data["customer"]))

        self.assertFalse(PDCheque.objects.filter(cheque_number="CHQ-ATTACK-01").exists())

    # ==========================================================================
    # 4. INACTIVE SHOP SUBSCRIPTION BLOCKING TESTS
    # ==========================================================================

    def test_inactive_shop_user_blocked_across_all_endpoints(self):
        """
        Users whose assigned shop has is_active=False must be strictly rejected
        with 403 PermissionDenied across all business endpoints.
        """
        self.client.force_authenticate(user=self.user_inactive)

        # 1. Inventory Products list & Category create
        res = self.client.get("/api/inventory/products/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Active shop membership required.", res.data["detail"])

        res = self.client.post("/api/inventory/categories/", data={"name": "Test"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Active shop membership required.", res.data["detail"])

        # 2. Sales Customers & Invoices
        res = self.client.get("/api/sales/customers/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.post(
            "/api/sales/invoices/",
            data={"payment_method": "CASH", "items": [{"product_id": 1, "quantity": 1}]},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Active shop membership required.", res.data["detail"])

        # 3. Owner Dashboard
        res = self.client.get("/api/sales/dashboard/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Active shop membership required.", res.data["detail"])

    # ==========================================================================
    # 5. UUID PUBLIC_ID LOOKUP & GENERATION TESTS (Phase 1A — Task 2b)
    # ==========================================================================

    def test_detail_endpoints_resolve_via_uuid_and_reject_integer_ids(self):
        """
        Detail endpoints must resolve cleanly when queried with UUID public_id,
        and must return 404 Not Found when queried with legacy integer IDs.
        """
        self.client.force_authenticate(user=self.owner_a)

        # 1. Category: Resolves with public_id, 404s with integer ID
        res_uuid = self.client.get(f"/api/inventory/categories/{self.category_a.public_id}/")
        self.assertEqual(res_uuid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_uuid.data["public_id"], str(self.category_a.public_id))

        res_int = self.client.get(f"/api/inventory/categories/{self.category_a.id}/")
        self.assertEqual(res_int.status_code, status.HTTP_404_NOT_FOUND)

        # 2. Product: Resolves with public_id, 404s with integer ID
        res_uuid = self.client.get(f"/api/inventory/products/{self.product_a.public_id}/")
        self.assertEqual(res_uuid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_uuid.data["public_id"], str(self.product_a.public_id))

        res_int = self.client.get(f"/api/inventory/products/{self.product_a.id}/")
        self.assertEqual(res_int.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Customer: Resolves with public_id, 404s with integer ID
        res_uuid = self.client.get(f"/api/sales/customers/{self.customer_a.public_id}/")
        self.assertEqual(res_uuid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_uuid.data["public_id"], str(self.customer_a.public_id))

        res_int = self.client.get(f"/api/sales/customers/{self.customer_a.id}/")
        self.assertEqual(res_int.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Invoice: Resolves with public_id, 404s with integer ID
        res_uuid = self.client.get(f"/api/sales/invoices/{self.invoice_a.public_id}/")
        self.assertEqual(res_uuid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_uuid.data["public_id"], str(self.invoice_a.public_id))

        res_int = self.client.get(f"/api/sales/invoices/{self.invoice_a.id}/")
        self.assertEqual(res_int.status_code, status.HTTP_404_NOT_FOUND)

        # 5. CreditPayment: Resolves with public_id, 404s with integer ID
        res_uuid = self.client.get(f"/api/sales/credit-payments/{self.credit_payment_a.public_id}/")
        self.assertEqual(res_uuid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_uuid.data["public_id"], str(self.credit_payment_a.public_id))

        res_int = self.client.get(f"/api/sales/credit-payments/{self.credit_payment_a.id}/")
        self.assertEqual(res_int.status_code, status.HTTP_404_NOT_FOUND)

        # 6. PDCheque: Resolves with public_id, 404s with integer ID
        res_uuid = self.client.get(f"/api/sales/pd-cheques/{self.pd_cheque_a.public_id}/")
        self.assertEqual(res_uuid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_uuid.data["public_id"], str(self.pd_cheque_a.public_id))

        res_int = self.client.get(f"/api/sales/pd-cheques/{self.pd_cheque_a.id}/")
        self.assertEqual(res_int.status_code, status.HTTP_404_NOT_FOUND)

    def test_newly_created_records_automatically_assigned_unique_uuid4_public_ids(self):
        """
        Every newly created model instance must automatically receive an immutable,
        unique UUID4 public_id, exposed in the serializer response.
        """
        self.client.force_authenticate(user=self.owner_a)

        # 1. Shop public_id check
        self.assertIsInstance(self.shop_a.public_id, uuid.UUID)
        self.assertIsInstance(self.shop_b.public_id, uuid.UUID)
        self.assertNotEqual(self.shop_a.public_id, self.shop_b.public_id)

        # 2. Create Category via API
        cat_res = self.client.post(
            "/api/inventory/categories/",
            data={"name": "New Fresh Produce"},
            format="json"
        )
        self.assertEqual(cat_res.status_code, status.HTTP_201_CREATED)
        self.assertIn("public_id", cat_res.data)
        cat_uuid = uuid.UUID(cat_res.data["public_id"])
        self.assertEqual(cat_uuid.version, 4)

        # 3. Create Product via API
        prod_res = self.client.post(
            "/api/inventory/products/",
            data={
                "name": "Fresh Organic Apples",
                "category": self.category_a.id,
                "barcode": "999888777",
                "cost_price": "150.00",
                "selling_price": "220.00",
                "stock_quantity": 40
            },
            format="json"
        )
        self.assertEqual(prod_res.status_code, status.HTTP_201_CREATED)
        self.assertIn("public_id", prod_res.data)
        prod_uuid = uuid.UUID(prod_res.data["public_id"])
        self.assertEqual(prod_uuid.version, 4)
        self.assertNotEqual(cat_uuid, prod_uuid)

        # 4. Create Customer via API
        cust_res = self.client.post(
            "/api/sales/customers/",
            data={
                "name": "Charlie Customer",
                "phone": "0733333333"
            },
            format="json"
        )
        self.assertEqual(cust_res.status_code, status.HTTP_201_CREATED)
        self.assertIn("public_id", cust_res.data)
        cust_uuid = uuid.UUID(cust_res.data["public_id"])
        self.assertEqual(cust_uuid.version, 4)
        self.assertNotEqual(prod_uuid, cust_uuid)
