from decimal import Decimal

from django.test import TestCase

from core.models import Shop, ShopSettings, User
from core.rbac import (
    ACTIVE_PERMISSIONS,
    RESERVED_PERMISSIONS,
    ROLE_PERMISSIONS,
    get_effective_permissions,
)


class RBACRegistryTests(TestCase):
    """
    Unit tests for the RBAC v2 Permission Registry, ShopSettings defaults,
    Manager delegation toggles, Accountant read-only guarantees, and feature flags.
    """

    def setUp(self):
        self.shop = Shop.objects.create(
            name="RBAC Test Mart",
            enable_credit_module=True,
            is_active=True,
        )
        self.owner = User.objects.create_user(
            username="rbac_owner",
            password="Password123!",
            shop=self.shop,
            role=User.Role.OWNER,
        )
        self.manager = User.objects.create_user(
            username="rbac_manager",
            password="Password123!",
            shop=self.shop,
            role=User.Role.MANAGER,
        )
        self.cashier = User.objects.create_user(
            username="rbac_cashier",
            password="Password123!",
            shop=self.shop,
            role=User.Role.CASHIER,
        )
        self.inventory_manager = User.objects.create_user(
            username="rbac_inv_mgr",
            password="Password123!",
            shop=self.shop,
            role=User.Role.INVENTORY_MANAGER,
        )
        self.accountant = User.objects.create_user(
            username="rbac_accountant",
            password="Password123!",
            shop=self.shop,
            role=User.Role.ACCOUNTANT,
        )

    def test_new_shop_auto_creates_shop_settings_with_safe_defaults(self):
        """Creating a new Shop auto-creates ShopSettings with 0.00 cashier discount and all manager toggles False."""
        settings = ShopSettings.objects.get(shop=self.shop)
        self.assertEqual(settings.cashier_max_discount_pct, Decimal('0.00'))
        self.assertFalse(settings.managers_can_edit_products)
        self.assertFalse(settings.managers_can_view_cost_price)
        self.assertFalse(settings.managers_can_view_profit)
        self.assertFalse(settings.managers_can_manage_purchasing)
        self.assertFalse(settings.managers_can_manage_cashiers)

    def test_user_has_non_null_unique_public_id(self):
        """Users created after the 3-step migration automatically receive a unique UUID public_id."""
        self.assertIsNotNone(self.owner.public_id)
        self.assertIsNotNone(self.cashier.public_id)
        self.assertNotEqual(self.owner.public_id, self.cashier.public_id)

    def test_effective_permissions_for_all_five_roles(self):
        """get_effective_permissions returns exact preset permissions when credit is enabled and toggles are off."""
        self.assertEqual(get_effective_permissions(self.owner), ACTIVE_PERMISSIONS)
        self.assertEqual(get_effective_permissions(self.manager), ROLE_PERMISSIONS['MANAGER'])
        self.assertEqual(get_effective_permissions(self.cashier), ROLE_PERMISSIONS['CASHIER'])
        self.assertEqual(
            get_effective_permissions(self.inventory_manager),
            ROLE_PERMISSIONS['INVENTORY_MANAGER'],
        )
        self.assertEqual(get_effective_permissions(self.accountant), ROLE_PERMISSIONS['ACCOUNTANT'])

        # Reserved permissions are not granted by default to OWNER
        for reserved in RESERVED_PERMISSIONS:
            self.assertNotIn(reserved, get_effective_permissions(self.owner))

    def test_accountant_is_strictly_view_only(self):
        """ACCOUNTANT has zero write permissions on customers, credit, cheques, inventory, or sales."""
        accountant_perms = get_effective_permissions(self.accountant)
        forbidden_writes = {
            'credit.manage_customers',
            'credit.record_payment',
            'cheques.manage',
            'inventory.manage_products',
            'inventory.adjust_stock',
            'inventory.csv_import',
            'sales.pos_checkout',
            'sales.apply_discount',
            'sales.void_invoice',
            'sales.return_invoice',
            'staff.manage',
            'staff.manage_cashiers_only',
            'settings.manage_shop',
        }
        self.assertTrue(accountant_perms.isdisjoint(forbidden_writes))
        # Confirm expected read permissions are present
        self.assertIn('credit.view_customers', accountant_perms)
        self.assertIn('credit.view_ledger', accountant_perms)
        self.assertIn('cheques.view', accountant_perms)
        self.assertIn('dashboard.view_profit', accountant_perms)
        self.assertIn('audit.view_all', accountant_perms)

    def test_shop_settings_toggles_affect_only_manager_not_cashier(self):
        """ShopSettings manager toggles dynamically grant/revoke permissions for MANAGER without affecting CASHIER."""
        settings = self.shop.settings
        cashier_before = get_effective_permissions(self.cashier)

        # Initially none of the 5 toggled permissions are granted to MANAGER
        manager_initial = get_effective_permissions(self.manager)
        self.assertNotIn('inventory.manage_products', manager_initial)
        self.assertNotIn('inventory.view_cost_price', manager_initial)
        self.assertNotIn('dashboard.view_profit', manager_initial)
        self.assertNotIn('purchasing.manage', manager_initial)
        self.assertNotIn('staff.manage_cashiers_only', manager_initial)

        # Enable all 5 manager toggles
        settings.managers_can_edit_products = True
        settings.managers_can_view_cost_price = True
        settings.managers_can_view_profit = True
        settings.managers_can_manage_purchasing = True
        settings.managers_can_manage_cashiers = True
        settings.save()

        manager_updated = get_effective_permissions(self.manager)
        self.assertIn('inventory.manage_products', manager_updated)
        self.assertIn('inventory.view_cost_price', manager_updated)
        self.assertIn('dashboard.view_profit', manager_updated)
        self.assertIn('purchasing.manage', manager_updated)
        self.assertIn('staff.manage_cashiers_only', manager_updated)

        # Cashier permissions must remain completely unchanged
        self.assertEqual(get_effective_permissions(self.cashier), cashier_before)

        # Revoke one toggle and verify immediate reflection
        settings.managers_can_view_profit = False
        settings.save()
        self.assertNotIn('dashboard.view_profit', get_effective_permissions(self.manager))

    def test_disabled_credit_module_strips_credit_and_cheques_for_all_roles(self):
        """enable_credit_module=False strips credit.* and cheques.* for every role including OWNER."""
        self.shop.enable_credit_module = False
        self.shop.save()

        for user in (self.owner, self.manager, self.cashier, self.inventory_manager, self.accountant):
            user.refresh_from_db()
            perms = get_effective_permissions(user)
            credit_or_cheque = [p for p in perms if p.startswith('credit.') or p.startswith('cheques.')]
            self.assertEqual(
                credit_or_cheque,
                [],
                f"Expected no credit/cheque permissions for {user.role}, found {credit_or_cheque}",
            )

    def test_inactive_user_or_shop_receives_empty_permissions(self):
        """Inactive users or users in inactive shops receive zero permissions."""
        self.cashier.is_active = False
        self.cashier.save()
        self.assertEqual(get_effective_permissions(self.cashier), frozenset())

        self.shop.is_active = False
        self.shop.save()
        self.owner.refresh_from_db()
        self.assertEqual(get_effective_permissions(self.owner), frozenset())
