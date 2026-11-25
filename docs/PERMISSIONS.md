# Modulr ERP — RBAC v2 Permission Registry & Role Matrix

This document is the authoritative specification for **RBAC v2** defined in [`backend/core/rbac.py`](../backend/core/rbac.py) and [`backend/core/models.py`](../backend/core/models.py).

---

## 1. Architecture Principles

- **Single Source of Truth:** All capabilities use `module.action` codes registered in `core.rbac.PERMISSIONS`.
- **Live Database Evaluation:** `get_effective_permissions(user) -> frozenset[str]` always evaluates against live database records (`User`, `Shop`, and `ShopSettings`), never stale JWT claims.
- **Tenant & User Active Checks:** Inactive users (`is_active=False`), users without a shop, or users belonging to suspended shops (`shop.is_active=False`) receive an empty permission set (`frozenset()`).
- **Feature-Flag Gating:** When `shop.enable_credit_module` is `False`, **all** `credit.*` and `cheques.*` permissions are stripped for **every** role—including `OWNER`.
- **Role Hierarchy (`ROLE_HIERARCHY`):**
  - `OWNER`: `100`
  - `MANAGER`: `80`
  - `INVENTORY_MANAGER`: `60`
  - `ACCOUNTANT`: `60`
  - `CASHIER`: `40`

---

## 2. Permission Catalog

### Active MVP Permissions

| Permission Code | Status | Description |
| :--- | :--- | :--- |
| `sales.pos_checkout` | `ACTIVE` | Process POS sales checkout and issue invoices |
| `sales.apply_discount` | `ACTIVE` | Apply discounts on POS invoices (subject to role/shop caps) |
| `sales.view_all_invoices` | `ACTIVE` | View all invoices across the shop |
| `sales.view_own_invoices` | `ACTIVE` | View only invoices created by the current user |
| `sales.void_invoice` | `ACTIVE` | Void finalized invoices and restore stock/credit |
| `sales.return_invoice` | `ACTIVE` | Process partial or full sales returns / credit notes |
| `inventory.view_products` | `ACTIVE` | View products, categories, and selling prices |
| `inventory.manage_products` | `ACTIVE` | Create, edit, and delete products and categories |
| `inventory.view_cost_price` | `ACTIVE` | View wholesale `cost_price` and `cost_price_at_sale` |
| `inventory.adjust_stock` | `ACTIVE` | Perform manual stock quantity adjustments |
| `inventory.csv_import` | `ACTIVE` | Bulk import/update products via CSV upload |
| `credit.lookup_customers` | `ACTIVE` | Look up customers during POS checkout |
| `credit.view_customers` | `ACTIVE` | View customer profiles and credit balances |
| `credit.manage_customers` | `ACTIVE` | Create, edit, and delete customer accounts |
| `credit.view_ledger` | `ACTIVE` | View customer credit payment history and ledger |
| `credit.record_payment` | `ACTIVE` | Record credit settlement payments from customers |
| `cheques.view` | `ACTIVE` | View post-dated cheques and upcoming due dates |
| `cheques.manage` | `ACTIVE` | Create, update, and change status of post-dated cheques |
| `dashboard.view_owner` | `ACTIVE` | View full owner executive dashboard |
| `dashboard.view_operational` | `ACTIVE` | View operational store dashboard (without profit if toggled off) |
| `dashboard.view_profit` | `ACTIVE` | View gross profit and margin analytics |
| `dashboard.view_cashier` | `ACTIVE` | View cashier personal shift/sales summary |
| `dashboard.view_inventory` | `ACTIVE` | View inventory-focused stock & reorder dashboard |
| `dashboard.view_finance` | `ACTIVE` | View financial, credit, and cheque analytics dashboard |
| `staff.manage` | `ACTIVE` | Create, update, and deactivate all non-owner staff roles |
| `staff.manage_cashiers_only` | `ACTIVE` | Create, update, and deactivate `CASHIER` accounts only |
| `settings.manage_shop` | `ACTIVE` | Modify shop profile, feature flags, and `ShopSettings` |
| `audit.view_all` | `ACTIVE` | View all shop-wide immutable audit log entries |
| `audit.view_staff` | `ACTIVE` | View audit log entries for staff operational actions |

### Reserved Phase-2 Permissions

| Permission Code | Status | Description |
| :--- | :--- | :--- |
| `purchasing.view` | `RESERVED` | View supplier purchase orders and bills (Phase 2) |
| `purchasing.manage` | `RESERVED` | Create and receive supplier purchase orders (Phase 2) |
| `expenses.view` | `RESERVED` | View store operating expenses (Phase 2) |
| `expenses.manage` | `RESERVED` | Record and categorize store operating expenses (Phase 2) |
| `shifts.manage_own` | `RESERVED` | Open and close own POS cash register shift (Phase 2) |
| `shifts.manage_all` | `RESERVED` | Review and reconcile all staff register shifts (Phase 2) |
| `reports.view_sales` | `RESERVED` | Export detailed sales breakdown reports (Phase 2) |
| `reports.view_stock` | `RESERVED` | Export stock valuation and movement reports (Phase 2) |

---

## 3. 5-Role MVP Matrix

Legend:
- **Yes**: Always granted (unless gated by `enable_credit_module=False`)
- **Toggle**: Granted to `MANAGER` only when the corresponding `ShopSettings` boolean is `True`
- **Credit Flag**: Stripped for all roles (including `OWNER`) when `Shop.enable_credit_module=False`
- **—**: Not granted

| Permission | OWNER | MANAGER | CASHIER | INVENTORY_MANAGER | ACCOUNTANT |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `sales.pos_checkout` | Yes | Yes | Yes | — | — |
| `sales.apply_discount` | Yes | Yes | Yes | — | — |
| `sales.view_all_invoices` | Yes | Yes | — | — | Yes |
| `sales.view_own_invoices` | Yes | — | Yes | — | — |
| `sales.void_invoice` | Yes | Yes | — | — | — |
| `sales.return_invoice` | Yes | Yes | — | — | — |
| `inventory.view_products` | Yes | Yes | Yes | Yes | Yes |
| `inventory.manage_products` | Yes | Toggle (`managers_can_edit_products`) | — | Yes | — |
| `inventory.view_cost_price` | Yes | Toggle (`managers_can_view_cost_price`) | — | Yes | Yes |
| `inventory.adjust_stock` | Yes | Yes | — | Yes | — |
| `inventory.csv_import` | Yes | — | — | Yes | — |
| `credit.lookup_customers` *(Credit Flag)* | Yes | Yes | Yes | — | — |
| `credit.view_customers` *(Credit Flag)* | Yes | Yes | — | — | Yes |
| `credit.manage_customers` *(Credit Flag)* | Yes | Yes | — | — | — |
| `credit.view_ledger` *(Credit Flag)* | Yes | Yes | — | — | Yes |
| `credit.record_payment` *(Credit Flag)* | Yes | Yes | — | — | — |
| `cheques.view` *(Credit Flag)* | Yes | Yes | — | — | Yes |
| `cheques.manage` *(Credit Flag)* | Yes | Yes | — | — | — |
| `dashboard.view_owner` | Yes | — | — | — | — |
| `dashboard.view_operational` | Yes | Yes | — | — | — |
| `dashboard.view_profit` | Yes | Toggle (`managers_can_view_profit`) | — | — | Yes |
| `dashboard.view_cashier` | Yes | — | Yes | — | — |
| `dashboard.view_inventory` | Yes | — | — | Yes | — |
| `dashboard.view_finance` | Yes | — | — | — | Yes |
| `staff.manage` | Yes | — | — | — | — |
| `staff.manage_cashiers_only` | Yes | Toggle (`managers_can_manage_cashiers`) | — | — | — |
| `settings.manage_shop` | Yes | — | — | — | — |
| `audit.view_all` | Yes | — | — | — | Yes |
| `audit.view_staff` | Yes | Yes | — | — | — |
| `purchasing.manage` *(Reserved)* | — | Toggle (`managers_can_manage_purchasing`) | — | — | — |

> **Note on `ACCOUNTANT`:** `ACCOUNTANT` is **strictly view-only** across all modules. It has zero write permissions (`credit.manage_customers`, `credit.record_payment`, `cheques.manage`, `inventory.manage_products`, `sales.pos_checkout`, etc. are all denied).

---

## 4. `ShopSettings` Delegation & Guardrails

Every `Shop` automatically receives a `ShopSettings` record on creation via `post_save` signal:

| Field | Default (New Shop) | Existing Shop Backfill | Effect |
| :--- | :---: | :---: | :--- |
| `managers_can_edit_products` | `False` | `False` | Grants `inventory.manage_products` to `MANAGER` |
| `managers_can_view_cost_price` | `False` | `False` | Grants `inventory.view_cost_price` to `MANAGER` |
| `managers_can_view_profit` | `False` | `False` | Grants `dashboard.view_profit` to `MANAGER` |
| `managers_can_manage_purchasing` | `False` | `False` | Grants `purchasing.manage` (Phase 2) to `MANAGER` |
| `managers_can_manage_cashiers` | `False` | `False` | Grants `staff.manage_cashiers_only` to `MANAGER` |
| `cashier_max_discount_pct` | `0.00` | `100.00` | Maximum invoice discount % a `CASHIER` may apply |
