from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import AuditLog, Shop, User
from inventory.models import Category, Product
from sales.models import Customer, Invoice, InvoiceItem, PDCheque


class PaginationFilteringAndSoftDeleteTests(APITestCase):
    """
    Tests for Task 4b:
    - Standardized PageNumberPagination (default 25, page_size, max_page_size=100)
    - django-filter FilterSets, SearchFilter, and OrderingFilter
    - Soft delete for Category, Product, and Customer with partial unique constraints
    - Customer debt guard & POST /{public_id}/restore/
    """

    def setUp(self):
        self.shop = Shop.objects.create(
            name="Pagination Mart",
            enable_credit_module=True,
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="pg_owner",
            password="Password123!",
            shop=self.shop,
            role=User.Role.OWNER,
        )
        self.category = Category.objects.create(shop=self.shop, name="Beverages")

    def test_pagination_page_size_and_max_cap(self):
        """Pagination supports ?page= & ?page_size= and caps page_size at max_page_size=100."""
        Product.objects.bulk_create([
            Product(
                shop=self.shop,
                category=self.category,
                name=f"Item {i:03d}",
                selling_price=Decimal('10.00'),
                stock_quantity=Decimal('20.000'),
            )
            for i in range(105)
        ])

        self.client.force_authenticate(user=self.owner)

        # Default page_size=25
        res_default = self.client.get('/api/inventory/products/')
        self.assertEqual(res_default.status_code, status.HTTP_200_OK)
        self.assertEqual(res_default.data['count'], 105)
        self.assertEqual(len(res_default.data['results']), 25)
        self.assertIsNotNone(res_default.data['next'])

        # Custom page=2&page_size=10
        res_p2 = self.client.get('/api/inventory/products/?page=2&page_size=10')
        self.assertEqual(res_p2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_p2.data['results']), 10)
        self.assertEqual(res_p2.data['results'][0]['name'], 'Item 010')

        # Exceeding max_page_size=100 is capped at 100
        res_cap = self.client.get('/api/inventory/products/?page_size=500')
        self.assertEqual(res_cap.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cap.data['results']), 100)

        # Upcoming cheques endpoint is also paginated
        PDCheque.objects.create(
            shop=self.shop,
            cheque_number='CHQ-1001',
            bank_name='Commercial Bank',
            amount=Decimal('5000.00'),
            due_date=timezone.now().date() + timedelta(days=2),
            status=PDCheque.Status.PENDING,
        )
        res_upcoming = self.client.get('/api/sales/pd-cheques/upcoming/')
        self.assertEqual(res_upcoming.status_code, status.HTTP_200_OK)
        self.assertIn('results', res_upcoming.data)
        self.assertEqual(res_upcoming.data['count'], 1)

    def test_filtering_search_and_ordering(self):
        """low_stock=true, status=VOIDED, date_from/date_to, has_credit=true, and ordering work."""
        p_low = Product.objects.create(
            shop=self.shop,
            category=self.category,
            name="Alpha Low",
            selling_price=Decimal('50.00'),
            stock_quantity=Decimal('2.000'),
            reorder_level=Decimal('5.000'),
        )
        Product.objects.create(
            shop=self.shop,
            category=self.category,
            name="Zeta High",
            selling_price=Decimal('200.00'),
            stock_quantity=Decimal('50.000'),
            reorder_level=Decimal('5.000'),
        )

        self.client.force_authenticate(user=self.owner)

        # low_stock=true
        res_low = self.client.get('/api/inventory/products/?low_stock=true')
        self.assertEqual(res_low.status_code, status.HTTP_200_OK)
        self.assertEqual([p['name'] for p in res_low.data['results']], ['Alpha Low'])

        # ordering=-selling_price
        res_ord = self.client.get('/api/inventory/products/?ordering=-selling_price')
        self.assertEqual([p['name'] for p in res_ord.data['results']], ['Zeta High', 'Alpha Low'])

        # Invoice status & date filtering
        today = timezone.now().date()
        Invoice.objects.create(
            shop=self.shop,
            invoice_number='INV-OK-1',
            cashier=self.owner,
            status=Invoice.Status.COMPLETED,
            subtotal=Decimal('50.00'),
            total_amount=Decimal('50.00'),
            amount_paid=Decimal('50.00'),
        )
        Invoice.objects.create(
            shop=self.shop,
            invoice_number='INV-VOID-1',
            cashier=self.owner,
            status=Invoice.Status.VOIDED,
            subtotal=Decimal('50.00'),
            total_amount=Decimal('50.00'),
            amount_paid=Decimal('50.00'),
        )

        res_void = self.client.get(
            f'/api/sales/invoices/?status=VOIDED&date_from={today}&date_to={today}'
        )
        self.assertEqual(res_void.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [inv['invoice_number'] for inv in res_void.data['results']],
            ['INV-VOID-1'],
        )

        # Customer has_credit=true
        Customer.objects.create(
            shop=self.shop, name="Debt Free", total_credit_balance=Decimal('0.00')
        )
        Customer.objects.create(
            shop=self.shop, name="Has Debt", total_credit_balance=Decimal('750.00')
        )
        res_credit = self.client.get('/api/sales/customers/?has_credit=true')
        self.assertEqual(res_credit.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [c['name'] for c in res_credit.data['results']],
            ['Has Debt'],
        )

        # Ensure p_low is referenced cleanly
        self.assertTrue(p_low.is_low_stock)

    def test_soft_delete_product_and_category_preserves_history_and_frees_barcode(self):
        """
        DELETE returns 204, hides from list/retrieve, preserves historical InvoiceItem FK,
        allows creating a new product with the same barcode, and logs SOFT_DELETED.
        """
        product = Product.objects.create(
            shop=self.shop,
            category=self.category,
            name="Old Tea",
            barcode="999888777666",
            selling_price=Decimal('100.00'),
            stock_quantity=Decimal('10.000'),
        )
        inv = Invoice.objects.create(
            shop=self.shop,
            invoice_number="INV-HIST-1",
            cashier=self.owner,
            subtotal=Decimal('100.00'),
            total_amount=Decimal('100.00'),
            amount_paid=Decimal('100.00'),
        )
        inv_item = InvoiceItem.objects.create(
            shop=self.shop,
            invoice=inv,
            product=product,
            quantity=Decimal('1.000'),
            unit_price=Decimal('100.00'),
            cost_price_at_sale=Decimal('60.00'),
            line_total=Decimal('100.00'),
        )

        self.client.force_authenticate(user=self.owner)

        # Soft-delete product
        del_res = self.client.delete(f'/api/inventory/products/{product.public_id}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

        # Hidden from list & retrieve (404)
        self.assertEqual(
            self.client.get('/api/inventory/products/').data['count'],
            0,
        )
        self.assertEqual(
            self.client.get(f'/api/inventory/products/{product.public_id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # Historical InvoiceItem still intact
        inv_item.refresh_from_db()
        self.assertEqual(inv_item.product_id, product.id)

        # AuditLog recorded SOFT_DELETED
        self.assertTrue(
            AuditLog.objects.filter(
                action='SOFT_DELETED',
                target_model='Product',
                target_id=str(product.public_id),
            ).exists()
        )

        # Creating a new product with the SAME barcode succeeds!
        new_prod_res = self.client.post(
            '/api/inventory/products/',
            data={
                'name': 'New Tea',
                'barcode': '999888777666',
                'selling_price': '120.00',
            },
            format='json',
        )
        self.assertEqual(new_prod_res.status_code, status.HTTP_201_CREATED)

        # Soft-delete category and recreate same name
        del_cat = self.client.delete(f'/api/inventory/categories/{self.category.public_id}/')
        self.assertEqual(del_cat.status_code, status.HTTP_204_NO_CONTENT)
        new_cat = self.client.post(
            '/api/inventory/categories/',
            data={'name': 'Beverages'},
            format='json',
        )
        self.assertEqual(new_cat.status_code, status.HTTP_201_CREATED)

    def test_customer_soft_delete_blocked_with_debt_allowed_when_zero(self):
        """Customer soft delete returns 400 if total_credit_balance > 0, and 204 when 0.00."""
        cust_debt = Customer.objects.create(
            shop=self.shop, name="Owing", total_credit_balance=Decimal('100.00')
        )
        cust_zero = Customer.objects.create(
            shop=self.shop, name="Settled", total_credit_balance=Decimal('0.00')
        )

        self.client.force_authenticate(user=self.owner)

        res_blocked = self.client.delete(f'/api/sales/customers/{cust_debt.public_id}/')
        self.assertEqual(res_blocked.status_code, status.HTTP_400_BAD_REQUEST)
        cust_debt.refresh_from_db()
        self.assertFalse(cust_debt.is_deleted)

        res_ok = self.client.delete(f'/api/sales/customers/{cust_zero.public_id}/')
        self.assertEqual(res_ok.status_code, status.HTTP_204_NO_CONTENT)
        cust_zero.refresh_from_db()
        self.assertTrue(cust_zero.is_deleted)

    def test_restore_soft_deleted_product_and_audit_log(self):
        """POST /{public_id}/restore/ restores a soft-deleted product and logs RESTORED."""
        product = Product.objects.create(
            shop=self.shop,
            name="Restorable Item",
            barcode="555444333222",
            selling_price=Decimal('90.00'),
        )
        self.client.force_authenticate(user=self.owner)

        self.assertEqual(
            self.client.delete(f'/api/inventory/products/{product.public_id}/').status_code,
            status.HTTP_204_NO_CONTENT,
        )

        restore_res = self.client.post(f'/api/inventory/products/{product.public_id}/restore/')
        self.assertEqual(restore_res.status_code, status.HTTP_200_OK)
        self.assertEqual(restore_res.data['name'], 'Restorable Item')

        product.refresh_from_db()
        self.assertFalse(product.is_deleted)
        self.assertIsNone(product.deleted_at)
        self.assertIsNone(product.deleted_by)

        self.assertTrue(
            AuditLog.objects.filter(
                action='RESTORED',
                target_model='Product',
                target_id=str(product.public_id),
            ).exists()
        )
