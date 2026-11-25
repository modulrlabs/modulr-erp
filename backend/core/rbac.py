"""
Central RBAC v2 Permission Registry and Effective Permission Evaluator.

WHY CENTRAL REGISTRY:
Instead of scattering ad-hoc role checks (`if user.role == 'OWNER'`) across views,
all capabilities are modeled as `module.action` permissions. Role presets,
ShopSettings manager toggles, and Shop feature flags are evaluated in one
authoritative place (`get_effective_permissions`) against live DB state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User


# ------------------------------------------------------------------------------
# Active MVP Permission Definitions (module.action -> human description)
# ------------------------------------------------------------------------------
ACTIVE_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    # Sales & POS
    'sales.pos_checkout': 'Process POS sales checkout and issue invoices',
    'sales.apply_discount': 'Apply discounts on POS invoices (subject to role/shop caps)',
    'sales.view_all_invoices': 'View all invoices across the shop',
    'sales.view_own_invoices': 'View only invoices created by the current user',
    'sales.void_invoice': 'Void finalized invoices and restore stock/credit',
    'sales.return_invoice': 'Process partial or full sales returns / credit notes',
    # Inventory
    'inventory.view_products': 'View products, categories, and selling prices',
    'inventory.manage_products': 'Create, edit, and delete products and categories',
    'inventory.view_cost_price': 'View wholesale cost_price and cost_price_at_sale',
    'inventory.adjust_stock': 'Perform manual stock quantity adjustments',
    'inventory.csv_import': 'Bulk import/update products via CSV upload',
    # Credit & Customers
    'credit.lookup_customers': 'Look up customers during POS checkout',
    'credit.view_customers': 'View customer profiles and credit balances',
    'credit.manage_customers': 'Create, edit, and delete customer accounts',
    'credit.view_ledger': 'View customer credit payment history and ledger',
    'credit.record_payment': 'Record credit settlement payments from customers',
    # Post-Dated Cheques
    'cheques.view': 'View post-dated cheques and upcoming due dates',
    'cheques.manage': 'Create, update, and change status of post-dated cheques',
    # Dashboards
    'dashboard.view_owner': 'View full owner executive dashboard',
    'dashboard.view_operational': 'View operational store dashboard (without profit if toggled off)',
    'dashboard.view_profit': 'View gross profit and margin analytics',
    'dashboard.view_cashier': 'View cashier personal shift/sales summary',
    'dashboard.view_inventory': 'View inventory-focused stock & reorder dashboard',
    'dashboard.view_finance': 'View financial, credit, and cheque analytics dashboard',
    # Staff Management
    'staff.manage': 'Create, update, and deactivate all non-owner staff roles',
    'staff.manage_cashiers_only': 'Create, update, and deactivate CASHIER accounts only',
    # Settings
    'settings.manage_shop': 'Modify shop profile, feature flags, and ShopSettings',
    # Audit Logs
    'audit.view_all': 'View all shop-wide immutable audit log entries',
    'audit.view_staff': 'View audit log entries for staff operational actions',
}

# ------------------------------------------------------------------------------
# Reserved Phase-2 Permissions (unbuilt modules; documented for roadmap parity)
# ------------------------------------------------------------------------------
RESERVED_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    'purchasing.view': 'View supplier purchase orders and bills (Phase 2)',
    'purchasing.manage': 'Create and receive supplier purchase orders (Phase 2)',
    'expenses.view': 'View store operating expenses (Phase 2)',
    'expenses.manage': 'Record and categorize store operating expenses (Phase 2)',
    'shifts.manage_own': 'Open and close own POS cash register shift (Phase 2)',
    'shifts.manage_all': 'Review and reconcile all staff register shifts (Phase 2)',
    'reports.view_sales': 'Export detailed sales breakdown reports (Phase 2)',
    'reports.view_stock': 'Export stock valuation and movement reports (Phase 2)',
}

ACTIVE_PERMISSIONS: frozenset[str] = frozenset(ACTIVE_PERMISSION_DESCRIPTIONS.keys())
RESERVED_PERMISSIONS: frozenset[str] = frozenset(RESERVED_PERMISSION_DESCRIPTIONS.keys())

PERMISSIONS: dict[str, dict[str, str]] = {
    **{
        code: {'description': desc, 'status': 'ACTIVE'}
        for code, desc in ACTIVE_PERMISSION_DESCRIPTIONS.items()
    },
    **{
        code: {'description': desc, 'status': 'RESERVED'}
        for code, desc in RESERVED_PERMISSION_DESCRIPTIONS.items()
    },
}


# ------------------------------------------------------------------------------
# Role Hierarchy & MVP Role Permission Presets
# ------------------------------------------------------------------------------
ROLE_HIERARCHY: dict[str, int] = {
    'OWNER': 100,
    'MANAGER': 80,
    'INVENTORY_MANAGER': 60,
    'ACCOUNTANT': 60,
    'CASHIER': 40,
}

# Mapping from ShopSettings boolean fields -> permission codes granted to MANAGER
MANAGER_SETTING_TOGGLES: tuple[tuple[str, str], ...] = (
    ('managers_can_edit_products', 'inventory.manage_products'),
    ('managers_can_view_cost_price', 'inventory.view_cost_price'),
    ('managers_can_view_profit', 'dashboard.view_profit'),
    ('managers_can_manage_purchasing', 'purchasing.manage'),
    ('managers_can_manage_cashiers', 'staff.manage_cashiers_only'),
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    'OWNER': ACTIVE_PERMISSIONS,
    'MANAGER': frozenset({
        'sales.pos_checkout',
        'sales.apply_discount',
        'sales.view_all_invoices',
        'sales.void_invoice',
        'sales.return_invoice',
        'inventory.view_products',
        'inventory.adjust_stock',
        'credit.lookup_customers',
        'credit.view_customers',
        'credit.manage_customers',
        'credit.view_ledger',
        'credit.record_payment',
        'cheques.view',
        'cheques.manage',
        'dashboard.view_operational',
        'audit.view_staff',
    }),
    'CASHIER': frozenset({
        'sales.pos_checkout',
        'sales.apply_discount',
        'sales.view_own_invoices',
        'inventory.view_products',
        'credit.lookup_customers',
        'dashboard.view_cashier',
    }),
    'INVENTORY_MANAGER': frozenset({
        'inventory.view_products',
        'inventory.manage_products',
        'inventory.view_cost_price',
        'inventory.adjust_stock',
        'inventory.csv_import',
        'dashboard.view_inventory',
    }),
    # ACCOUNTANT is STRICTLY VIEW-ONLY across financial, ledger, cheque, and audit views.
    'ACCOUNTANT': frozenset({
        'sales.view_all_invoices',
        'inventory.view_products',
        'inventory.view_cost_price',
        'credit.view_customers',
        'credit.view_ledger',
        'cheques.view',
        'dashboard.view_profit',
        'dashboard.view_finance',
        'audit.view_all',
    }),
}


def get_effective_permissions(user: User | None) -> frozenset[str]:
    """
    Evaluate effective permissions from live DB state (`user`, `user.shop`, `ShopSettings`).

    Never reads permissions from JWT claims so role changes, ShopSettings toggles,
    and subscription feature-flag changes take effect immediately.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return frozenset()

    shop = getattr(user, 'shop', None)
    if not shop or not shop.is_active:
        return frozenset()

    perms = set(ROLE_PERMISSIONS.get(user.role, frozenset()))

    # Apply ShopSettings toggles exclusively for MANAGER role
    if user.role == 'MANAGER':
        from .models import ShopSettings

        shop_settings = ShopSettings.objects.filter(shop_id=shop.id).first()
        if shop_settings:
            for field_name, perm_code in MANAGER_SETTING_TOGGLES:
                if getattr(shop_settings, field_name, False):
                    perms.add(perm_code)

    # Feature-flag gating: strip credit.* and cheques.* if credit module is disabled
    if not shop.enable_credit_module:
        perms = {
            p for p in perms
            if not (p.startswith('credit.') or p.startswith('cheques.'))
        }

    return frozenset(perms)
