from decimal import Decimal

from axes.models import AccessAttempt
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import AuditLog, Shop, User
from inventory.models import Category, Product
from sales.models import Customer, PDCheque


class AuditLogImmutabilityTests(APITestCase):
    """
    Test suite verifying the absolute immutability of AuditLog instances.
    AuditLog entries must never be modified or deleted via ORM methods or bulk queries.
    """

    def setUp(self):
        cache.clear()
        AccessAttempt.objects.all().delete()
        self.shop = Shop.objects.create(name="Audit Test Shop", is_active=True)
        self.user = User.objects.create_user(
            username="auditor",
            password="password123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.log_entry = AuditLog.objects.create(
            shop=self.shop,
            actor=self.user,
            actor_username="auditor",
            action="TEST_ACTION",
            target_model="TestModel",
            target_id="12345",
            before_state={"val": 1},
            after_state={"val": 2},
        )

    def test_save_on_existing_log_raises_value_error(self):
        """Calling save() on an already persisted AuditLog must raise ValueError."""
        self.log_entry.action = "TAMPERED_ACTION"
        with self.assertRaises(ValueError) as ctx:
            self.log_entry.save()
        self.assertIn("AuditLog entries are immutable and cannot be modified.", str(ctx.exception))

    def test_delete_on_log_instance_raises_value_error(self):
        """Calling delete() on an AuditLog instance must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.log_entry.delete()
        self.assertIn("AuditLog entries are immutable and cannot be deleted.", str(ctx.exception))

    def test_bulk_update_raises_value_error(self):
        """Calling .update() on an AuditLog queryset must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            AuditLog.objects.filter(id=self.log_entry.id).update(action="HACKED")
        self.assertIn("AuditLog entries are immutable and cannot be modified.", str(ctx.exception))

    def test_bulk_delete_raises_value_error(self):
        """Calling .delete() on an AuditLog queryset must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            AuditLog.objects.all().delete()
        self.assertIn("AuditLog entries are immutable and cannot be deleted.", str(ctx.exception))


class AuditLogTriggerTests(APITestCase):
    """
    Test suite verifying that critical business actions automatically emit AuditLog entries
    with correct before/after states and sensitive data redaction.
    """

    def setUp(self):
        cache.clear()
        AccessAttempt.objects.all().delete()
        self.csrf_headers = {
            "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
            "HTTP_ORIGIN": "http://localhost:5173",
        }
        self.shop = Shop.objects.create(name="Trigger Test Shop", enable_credit_module=True, is_active=True)
        self.owner = User.objects.create_user(
            username="owner_trigger",
            password="owner_password_123",
            shop=self.shop,
            role=User.Role.OWNER
        )
        self.cashier = User.objects.create_user(
            username="cashier_trigger",
            password="cashier_password_123",
            shop=self.shop,
            role=User.Role.CASHIER
        )
        self.category = Category.objects.create(shop=self.shop, name="Groceries")
        self.product = Product.objects.create(
            shop=self.shop,
            category=self.category,
            name="Milk 1L",
            barcode="555001",
            cost_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            stock_quantity=50
        )
        self.customer = Customer.objects.create(
            shop=self.shop,
            name="Jane Doe",
            phone="0712345678",
            total_credit_balance=Decimal("500.00")
        )

    def test_login_success_and_logout_triggers(self):
        """Successful login and logout must record AuditLog events without exposing tokens."""
        # 1. Login
        login_res = self.client.post("/api/auth/login/", data={
            "username": "owner_trigger",
            "password": "owner_password_123"
        }, format="json")
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        login_log = AuditLog.objects.filter(action="LOGIN_SUCCESS", actor_username="owner_trigger").first()
        self.assertIsNotNone(login_log)
        self.assertEqual(login_log.target_model, "User")
        self.assertEqual(login_log.after_state.get("username"), "owner_trigger")
        # Ensure password is NOT leaked in any state
        self.assertNotIn("owner_password_123", str(login_log.before_state))
        self.assertNotIn("owner_password_123", str(login_log.after_state))

        # 2. Logout
        self.client.force_authenticate(user=self.owner)
        logout_res = self.client.post("/api/auth/logout/", **self.csrf_headers)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        logout_log = AuditLog.objects.filter(action="LOGOUT", actor_username="owner_trigger").first()
        self.assertIsNotNone(logout_log)

    def test_login_failed_trigger_and_password_redaction(self):
        """Failed login must record LOGIN_FAILED without leaking raw attempted password."""
        bad_password = "SecretPassword999!"
        self.client.post("/api/auth/login/", data={
            "username": "owner_trigger",
            "password": bad_password
        }, format="json")

        fail_log = AuditLog.objects.filter(action="LOGIN_FAILED", actor_username="owner_trigger").first()
        self.assertIsNotNone(fail_log)
        self.assertEqual(fail_log.before_state.get("attempted_username"), "owner_trigger")
        self.assertNotIn(bad_password, str(fail_log.before_state))
        self.assertNotIn(bad_password, str(fail_log.after_state))

    def test_product_price_and_stock_change_triggers(self):
        """Product price and stock updates must generate distinct audit records with exact changes."""
        self.client.force_authenticate(user=self.owner)

        # 1. Price update
        res = self.client.patch(
            f"/api/inventory/products/{self.product.public_id}/",
            data={"selling_price": "180.00"},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        price_log = AuditLog.objects.filter(action="PRODUCT_PRICE_CHANGED").first()
        self.assertIsNotNone(price_log)
        self.assertEqual(price_log.before_state["selling_price"], "150.00")
        self.assertEqual(price_log.after_state["selling_price"], "180.00")

        # 2. Stock update
        res = self.client.patch(
            f"/api/inventory/products/{self.product.public_id}/",
            data={"stock_quantity": 75},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        stock_log = AuditLog.objects.filter(action="PRODUCT_STOCK_CHANGED").first()
        self.assertIsNotNone(stock_log)
        self.assertEqual(stock_log.before_state["stock_quantity"], "50.000")
        self.assertEqual(stock_log.after_state["stock_quantity"], "75.000")

    def test_csv_import_trigger(self):
        """Bulk CSV upload must emit CSV_IMPORT audit record with summary metrics."""
        self.client.force_authenticate(user=self.owner)

        csv_content = (
            "name,barcode,category,cost_price,selling_price,stock_quantity,reorder_level\n"
            "Item One,BC-101,Groceries,20.00,30.00,10,2\n"
            "Item Two,BC-102,Groceries,40.00,60.00,20,5\n"
        )
        csv_file = SimpleUploadedFile("inventory.csv", csv_content.encode("utf-8"), content_type="text/csv")

        res = self.client.post("/api/inventory/products/upload-csv/", data={"file": csv_file}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        csv_log = AuditLog.objects.filter(action="CSV_IMPORT").first()
        self.assertIsNotNone(csv_log)
        self.assertEqual(csv_log.after_state["created_count"], 2)

    def test_invoice_creation_and_discount_triggers(self):
        """POS Checkout with discount must generate INVOICE_CREATED and DISCOUNT_APPLIED logs."""
        self.shop.settings.cashier_max_discount_pct = Decimal('10.00')
        self.shop.settings.save()
        self.client.force_authenticate(user=self.cashier)

        payload = {
            "payment_method": "CASH",
            "discount": "25.00",
            "amount_paid": "275.00",
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": 2
                }
            ]
        }

        res = self.client.post("/api/sales/invoices/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Verify INVOICE_CREATED
        inv_log = AuditLog.objects.filter(action="INVOICE_CREATED").first()
        self.assertIsNotNone(inv_log)
        self.assertEqual(inv_log.target_model, "Invoice")

        # Verify DISCOUNT_APPLIED
        disc_log = AuditLog.objects.filter(action="DISCOUNT_APPLIED").first()
        self.assertIsNotNone(disc_log)
        self.assertEqual(disc_log.after_state["discount"], "25.00")

    def test_credit_payment_trigger(self):
        """Credit settlement must record CREDIT_PAYMENT_RECORDED with before/after debt balance."""
        self.client.force_authenticate(user=self.owner)

        res = self.client.post("/api/sales/credit-payments/", data={
            "customer": self.customer.id,
            "amount_paid": "200.00",
            "payment_method": "CASH"
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        pay_log = AuditLog.objects.filter(action="CREDIT_PAYMENT_RECORDED").first()
        self.assertIsNotNone(pay_log)
        self.assertEqual(pay_log.before_state["total_credit_balance"], "500.00")
        self.assertEqual(pay_log.after_state["total_credit_balance"], "300.00")

    def test_pd_cheque_status_update_trigger(self):
        """Updating PD cheque clearance status must record PD_CHEQUE_UPDATED."""
        self.client.force_authenticate(user=self.owner)

        cheque = PDCheque.objects.create(
            shop=self.shop,
            customer=self.customer,
            cheque_number="CHQ-99001",
            bank_name="HNB",
            amount=Decimal("1500.00"),
            due_date=timezone.now().date()
        )

        res = self.client.patch(
            f"/api/sales/pd-cheques/{cheque.public_id}/",
            data={"status": "CLEARED"},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        cheque_log = AuditLog.objects.filter(action="PD_CHEQUE_UPDATED").first()
        self.assertIsNotNone(cheque_log)
        self.assertEqual(cheque_log.before_state["status"], "PENDING")
        self.assertEqual(cheque_log.after_state["status"], "CLEARED")


class AuditLogEndpointSecurityTests(APITestCase):
    """
    Test suite for RBAC and Multi-Tenant Isolation on the GET /api/core/audit-logs/ endpoint.
    """

    def setUp(self):
        cache.clear()
        AccessAttempt.objects.all().delete()

        # Tenant A
        self.shop_a = Shop.objects.create(name="Shop Alpha", is_active=True)
        self.owner_a = User.objects.create_user(
            username="owner_a",
            password="password123",
            shop=self.shop_a,
            role=User.Role.OWNER
        )
        self.cashier_a = User.objects.create_user(
            username="cashier_a",
            password="password123",
            shop=self.shop_a,
            role=User.Role.CASHIER
        )
        self.log_a = AuditLog.objects.create(
            shop=self.shop_a,
            actor=self.owner_a,
            actor_username="owner_a",
            action="PRODUCT_CREATED",
            target_model="Product",
            target_id="prod-alpha-1"
        )

        # Tenant B
        self.shop_b = Shop.objects.create(name="Shop Beta", is_active=True)
        self.owner_b = User.objects.create_user(
            username="owner_b",
            password="password123",
            shop=self.shop_b,
            role=User.Role.OWNER
        )
        self.log_b = AuditLog.objects.create(
            shop=self.shop_b,
            actor=self.owner_b,
            actor_username="owner_b",
            action="PRODUCT_CREATED",
            target_model="Product",
            target_id="prod-beta-1"
        )

    def test_cashier_forbidden_from_viewing_audit_logs(self):
        """Cashiers must receive 403 Forbidden when accessing audit logs."""
        self.client.force_authenticate(user=self.cashier_a)
        res = self.client.get("/api/core/audit-logs/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_isolation_on_audit_logs(self):
        """Owner A cannot list or retrieve Owner B's audit logs."""
        self.client.force_authenticate(user=self.owner_a)

        # 1. List logs: only Shop A logs returned
        res = self.client.get("/api/core/audit-logs/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        log_ids = [entry["public_id"] for entry in res.data["results"]]
        self.assertIn(str(self.log_a.public_id), log_ids)
        self.assertNotIn(str(self.log_b.public_id), log_ids)

        # 2. Detail lookup on Shop B log returns 404
        detail_res = self.client.get(f"/api/core/audit-logs/{self.log_b.public_id}/")
        self.assertEqual(detail_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_audit_log_filtering_and_search(self):
        """Filtering by ?action= and ?target_model= and ?search= works correctly."""
        self.client.force_authenticate(user=self.owner_a)

        # Filter by action
        res = self.client.get("/api/core/audit-logs/?action=PRODUCT_CREATED")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)

        res_none = self.client.get("/api/core/audit-logs/?action=NON_EXISTENT")
        self.assertEqual(res_none.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_none.data["results"]), 0)

        # Filter by target_model
        res_model = self.client.get("/api/core/audit-logs/?target_model=Product")
        self.assertEqual(res_model.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_model.data["results"]), 1)

        # Search by target_id
        res_search = self.client.get("/api/core/audit-logs/?search=prod-alpha")
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_search.data["results"]), 1)
