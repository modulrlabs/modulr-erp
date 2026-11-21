# System Architecture & AI Coding Guidelines
**Project:** Modular Multi-Tenant ERP + POS SaaS  
**Backend:** Python 3.11+ / Django 5 / Django REST Framework (DRF) / PostgreSQL  
**Frontend:** React (Vite) / TypeScript / Tailwind CSS  
**Target Audience:** Undergraduate Developer & Educational AI Collaboration  

---

## 1. System Overview & Philosophy

This project is a multi-tenant, modular Enterprise Resource Planning (ERP) and Point of Sale (POS) system designed for small to medium retail and wholesale businesses.

### Architectural Pillars
1. **Strict Data Isolation (Row-Level Multi-Tenancy):** Every business entity belongs exclusively to one `Shop`. Cross-tenant data leaks are catastrophic security failures.
2. **Dynamic Modularity (Feature Toggles):** Shops can toggle advanced business features (e.g., Credit Accounts, Cheque Processing, WhatsApp Receipts) without requiring code modifications or custom deployments.
3. **Educational Codebase ("Why-First" Engineering):** Every complex architectural decision, security check, or data transformation must be accompanied by beginner-friendly documentation and in-code comments explaining **why** it exists, allowing the student developer to learn industry-standard software engineering while building.

---

## 2. Non-Negotiable Directives for AI Coding Assistants

> [!IMPORTANT]
> **To all AI Assistants (Gemini, Claude, Copilot, ChatGPT, Antigravity, Cursor):**
> You MUST follow these mandatory rules when generating, refactoring, or reviewing code in this repository:
> 
> 1. **Multi-Tenancy Rule:** Every business database model MUST link directly to `Shop` via a `ForeignKey`. All queries in views, viewsets, and services MUST explicitly filter by `request.user.shop`. Never accept `shop_id` from client request bodies or URL parameters for write operations.
> 2. **Modularity Rule:** Endpoints, services, and UI components belonging to optional modules (e.g., Credit, Cheques, WhatsApp) MUST be guarded by feature flags configured on the `Shop` model.
> 3. **Educational Style Rule:** Write clean, readable code with descriptive comments that explain the **"WHY"** (architectural reasons, security implications, accounting principles, trade-offs), not just the "WHAT".
> 4. **Financial & Data Integrity Rule:** All multi-step POS/ERP operations (e.g., creating a sale, deducting stock, updating customer credit balance) MUST be wrapped inside `transaction.atomic()`.

---

## 3. Rule 1: Multi-Tenancy Architecture (Row-Level Isolation)

### 3.1 Multi-Tenancy Model: Shared Database, Shared Schema, Row Isolation
In this architecture, all shops share a single PostgreSQL database and table schemas. Isolation is guaranteed at the row level via a discriminator foreign key (`shop_id`).

```
                    ┌────────────────────────────┐
                    │        Shop (Tenant)       │
                    └──────────────┬─────────────┘
                                   │ 1
                                   │
                    ┌──────────────┴─────────────┐
                    │ *                          │ *
         ┌──────────┴──────────┐      ┌──────────┴──────────┐
         │     User / Staff    │      │   Business Model    │
         │  (Cashier, Manager) │      │ (Product, Sale, etc)│
         └─────────────────────┘      └─────────────────────┘
```

### 3.2 The Abstract Base Model (`ShopAwareModel`)
All business models (products, categories, sales, customers, suppliers, inventory logs) **MUST inherit from `ShopAwareModel`**.

#### Implementation (`backend/apps/common/models.py`):
```python
from django.db import models
from apps.shops.models import Shop

class ShopAwareModel(models.Model):
    """
    Abstract base model that enforces row-level multi-tenancy.
    
    WHY:
    1. DRY Principle: Guarantees that every business entity has a 'shop' reference 
       without rewriting the field definition on dozens of models.
    2. Cascade Protection: If a shop account is deleted or archived, all associated 
       business data is cleanly removed or handled.
    3. Indexing: Adding db_index=True on shop_id is critical because 100% of 
       production queries will filter by this column.
    """
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
        help_text="The tenant/shop that owns this record."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the record was created for audit trails."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last modified."
    )

    class Meta:
        abstract = True
```

### 3.3 Query Isolation & The Custom Tenant Manager
To prevent accidental cross-tenant data leaks, models should utilize a custom manager or queryset that scopes records to a specific shop.

```python
from django.db import models

class TenantQuerySet(models.QuerySet):
    """
    Custom QuerySet providing convenient shop-scoped filters.
    """
    def for_shop(self, shop):
        # WHY: Provides a reusable, chainable method to restrict results to a tenant
        return self.filter(shop=shop)

class TenantManager(models.Manager):
    """
    Manager that ensures queries can easily be scoped by tenant.
    """
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_shop(self, shop):
        return self.get_queryset().for_shop(shop)
```

### 3.4 Controller / ViewSet Rules (DRF)
In Django REST Framework `GenericAPIView` or `ModelViewSet`:

#### Rule A: `get_queryset()` MUST filter by `request.user.shop`
```python
from rest_framework import viewsets, permissions
from apps.inventory.models import Product
from apps.inventory.serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        WHY:
        Never return Product.objects.all(). An unauthenticated or malicious user 
        could list inventory belonging to competing shops.
        Always scope the base queryset to the authenticated user's shop.
        """
        # User must belong to an active shop
        user = self.request.user
        return Product.objects.filter(shop=user.shop)

    def perform_create(self, serializer):
        """
        WHY:
        Never allow the frontend to specify the 'shop' field in the request payload. 
        A malicious client could attempt to inject records into another shop's database.
        The backend must strictly attach the authenticated user's shop.
        """
        serializer.save(shop=self.request.user.shop)
```

#### Rule B: Cross-Tenant Foreign Key Integrity
When creating a record that references another entity (e.g., adding an item to a `Sale` that points to a `Product` and `Customer`):
```python
# In SaleItemSerializer or SaleService:
def validate(self, attrs):
    user_shop = self.context['request'].user.shop
    product = attrs.get('product')
    customer = attrs.get('customer')

    # WHY: Prevent 'ID Spoofing'. Even if a user owns Shop A, they must not 
    # link a Product ID belonging to Shop B into their sale.
    if product and product.shop != user_shop:
        raise serializers.ValidationError({"product": "Selected product does not belong to your shop."})

    if customer and customer.shop != user_shop:
        raise serializers.ValidationError({"customer": "Selected customer does not belong to your shop."})

    return attrs
```

---

## 4. Rule 2: Modularity & Feature Flag Architecture

### 4.1 Feature Toggles on the `Shop` Model
Every shop has a different operational profile. For example:
- A small roadside retail store needs POS, but does not need credit accounts or cheque tracking.
- A wholesale distributor needs customer credit, cheques, and bulk pricing.
- An upscale boutique wants automated WhatsApp PDF invoices sent to customers.

Features must be toggled on/off on the `Shop` model via boolean fields or a JSON configuration.

#### Model Definition (`backend/apps/shops/models.py`):
```python
from django.db import models

class Shop(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name="owned_shops")
    
    # --------------------------------------------------------------------------
    # Modular Feature Flags
    # WHY: Boolean flags provide simple, indexable, and performant permission checks.
    # New features should be toggled off by default unless included in standard tier.
    # --------------------------------------------------------------------------
    enable_credit_sales = models.BooleanField(
        default=False,
        help_text="Enables customer credit ledger, balance tracking, and pay-later terms."
    )
    enable_cheque_tracking = models.BooleanField(
        default=False,
        help_text="Enables cheque acceptance, clearance status, and bank deposit tracking."
    )
    enable_whatsapp_notifications = models.BooleanField(
        default=False,
        help_text="Enables sending PDF invoices and transaction receipts via WhatsApp API."
    )
    enable_barcode_scanner = models.BooleanField(
        default=True,
        help_text="Enables fast barcode lookup in the POS checkout screen."
    )
    
    def __str__(self):
        return self.name
```

### 4.2 Backend Enforcement: Custom DRF Permissions
Never rely solely on the frontend to hide disabled features. The backend API must reject unauthorized requests with `403 Forbidden`.

#### Permission Class (`backend/apps/common/permissions.py`):
```python
from rest_framework import permissions

def require_shop_feature(feature_attr_name: str):
    """
    Factory that returns a DRF Permission class checking a specific Shop feature flag.
    
    WHY:
    Keeps code DRY. Instead of writing separate permission classes for Cheques, 
    Credit, and WhatsApp, we generate dynamic permission classes with clear error messages.
    """
    class FeaturePermission(permissions.BasePermission):
        message = f"This feature ({feature_attr_name}) is not enabled for your shop subscription."

        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            
            shop = getattr(request.user, 'shop', None)
            if not shop:
                return False
            
            # Check if the shop model has this boolean attribute set to True
            return bool(getattr(shop, feature_attr_name, False))

    return FeaturePermission
```

#### Usage in Views (`backend/apps/finance/views.py`):
```python
from rest_framework import viewsets
from apps.common.permissions import require_shop_feature
from .models import Cheque
from .serializers import ChequeSerializer

class ChequeViewSet(viewsets.ModelViewSet):
    """
    Manages customer and supplier cheques.
    Guarded so shops without 'enable_cheque_tracking' cannot access these endpoints.
    """
    serializer_class = ChequeSerializer
    permission_classes = [require_shop_feature('enable_cheque_tracking')]

    def get_queryset(self):
        return Cheque.objects.filter(shop=self.request.user.shop)
```

### 4.3 Frontend Enforcement: Dynamic UI via Config Hooks
On the React frontend, the user's active shop configuration is loaded upon login and made available via React Context.

#### TypeScript Interface (`frontend/src/types/shop.ts`):
```typescript
export interface ShopFeatures {
  enable_credit_sales: boolean;
  enable_cheque_tracking: boolean;
  enable_whatsapp_notifications: boolean;
  enable_barcode_scanner: boolean;
}

export interface Shop {
  id: number;
  name: string;
  features: ShopFeatures;
}
```

#### Custom Hook (`frontend/src/hooks/useFeatureFlag.ts`):
```typescript
import { useAuth } from '../context/AuthContext';

/**
 * Hook to check if a specific modular feature is enabled for the current shop.
 * 
 * WHY:
 * Centralizes feature checking in UI components. If feature naming or resolution
 * logic changes in the future, we only have to update this single hook.
 * 
 * Example:
 * const hasCheques = useFeatureFlag('enable_cheque_tracking');
 * if (!hasCheques) return null;
 */
export const useFeatureFlag = (flagName: keyof ShopFeatures): boolean => {
  const { currentShop } = useAuth();
  
  if (!currentShop?.features) {
    return false;
  }
  
  return Boolean(currentShop.features[flagName]);
};
```

#### Conditional Component Rendering Example:
```tsx
// In CheckoutPaymentModal.tsx
import React from 'react';
import { useFeatureFlag } from '../hooks/useFeatureFlag';

export const PaymentMethodSelector: React.FC = () => {
  const canUseCredit = useFeatureFlag('enable_credit_sales');
  const canUseCheque = useFeatureFlag('enable_cheque_tracking');

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Cash is always available for all shops */}
      <button className="btn-payment">Cash</button>
      <button className="btn-payment">Credit/Debit Card</button>

      {/* Credit sale option rendered ONLY if shop has enabled it */}
      {canUseCredit && (
        <button className="btn-payment bg-amber-50 border-amber-200">
          Store Credit (Pay Later)
        </button>
      )}

      {/* Cheque option rendered ONLY if shop has enabled it */}
      {canUseCheque && (
        <button className="btn-payment bg-blue-50 border-blue-200">
          Cheque
        </button>
      )}
    </div>
  );
};
```

---

## 5. Rule 3: Educational Code Style & "Why" Comments

### 5.1 The "Why" Comment Standard
The developer is an undergraduate student actively learning SaaS software architecture. Every AI assistant or contributor must annotate non-obvious code with concise explanations answering:
1. **Why was this approach chosen over an alternative?**
2. **What edge case, security vulnerability, or race condition does this prevent?**
3. **What domain/business rule (accounting, inventory) does this satisfy?**

#### ❌ Bad Comment (Explaining the Obvious "What"):
```python
# Filter products by shop
products = Product.objects.filter(shop=request.user.shop)

# Loop over items
for item in items:
    # Save the item
    item.save()
```

#### ✅ Good Comment (Explaining the Critical "Why"):
```python
# WHY: We must scope query directly to request.user.shop to guarantee tenant isolation.
# Even if the client passed ?shop_id=99 in query parameters, we completely ignore it 
# to prevent IDOR (Insecure Direct Object Reference) vulnerabilities.
products = Product.objects.filter(shop=request.user.shop)

# WHY: Wrap inventory deductions in transaction.atomic() with select_for_update().
# In a high-traffic POS environment, two cashiers could ring up the last available 
# item simultaneously. select_for_update() locks the row until the transaction commits,
# preventing overselling (negative stock race condition).
with transaction.atomic():
    product = Product.objects.select_for_update().get(id=product_id, shop=request.user.shop)
    if product.stock_quantity < quantity:
        raise InsufficientStockError(f"Only {product.stock_quantity} units remaining.")
    product.stock_quantity -= quantity
    product.save()
```

### 5.2 Python & DRF Standards
- **Type Annotations:** Use Python type hints (`typing.Optional`, `typing.List`, etc.) on all service methods and utility functions.
- **Service Layer Pattern:** Keep views and serializers thin. Complex business workflows (e.g., `CompleteSaleService`, `ReconcileChequeService`) live in `apps/<domain>/services.py`.
- **Custom Exceptions:** Raise domain-specific exceptions (e.g., `FeatureDisabledException`, `InsufficientStockError`) and map them to standard DRF error responses.

### 5.3 React & TypeScript Standards
- **Strict Typing:** No `any`. Define clean interfaces for all API response payloads, models, and component props.
- **Component Organization:** Follow atomic or feature-based structure:
  - `components/ui/`: Reusable, generic UI primitives (buttons, inputs, modals).
  - `features/<feature-name>/`: Domain-specific components (e.g., `features/pos/`, `features/inventory/`).
  - `hooks/`: Custom hooks for data fetching, caching, and state management.
- **Tailwind Cleanliness:** Group utility classes logically (Layout -> Spacing -> Typography -> Colors -> State/Hover).

---

## 6. Financial Integrity & POS Transaction Safety

### 6.1 Atomic Database Transactions
In an ERP/POS system, creating a sale involves multiple interdependent database writes:
1. Creating the `Sale` header record.
2. Creating `SaleItem` records.
3. Decrementing `Product.stock_quantity`.
4. Creating an `InventoryMovementLog` entry for audit trails.
5. If payment is via credit, updating the customer's ledger balance.

> [!CAUTION]
> If step 4 or 5 fails (e.g. database glitch, network timeout), steps 1–3 MUST NOT remain saved in the database.
> **All checkout operations MUST use `transaction.atomic()`.**

```python
from django.db import transaction
from rest_framework.exceptions import ValidationError

class SaleService:
    @staticmethod
    def process_checkout(user, sale_data: dict) -> Sale:
        """
        Processes a full POS sale transaction safely.
        """
        shop = user.shop

        # WHY: Atomic block ensures all-or-nothing execution. 
        # If any step raises an exception, the entire checkout rolls back.
        with transaction.atomic():
            # 1. Create sale record
            sale = Sale.objects.create(
                shop=shop,
                cashier=user,
                total_amount=sale_data['total_amount'],
                payment_method=sale_data['payment_method']
            )

            # 2. Iterate and deduct stock safely
            for item in sale_data['items']:
                # Row-level lock to prevent concurrent checkout race condition
                product = Product.objects.select_for_update().get(
                    id=item['product_id'], 
                    shop=shop
                )
                
                if product.stock_quantity < item['quantity']:
                    # Raising an exception here triggers automatic transaction rollback
                    raise ValidationError(f"Insufficient stock for {product.name}.")

                product.stock_quantity -= item['quantity']
                product.save(update_fields=['stock_quantity', 'updated_at'])

                SaleItem.objects.create(
                    shop=shop,
                    sale=sale,
                    product=product,
                    quantity=item['quantity'],
                    unit_price=product.price
                )

            return sale
```

---

## 7. Recommended Repository Layout

```
businezz-erp/
├── backend/
│   ├── manage.py
│   ├── config/                  # Django project root (settings, urls, wsgi)
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   └── production.py
│   │   └── urls.py
│   ├── apps/
│   │   ├── common/              # Abstract base models, permissions, pagination
│   │   │   ├── models.py        # ShopAwareModel, TimestampedModel
│   │   │   └── permissions.py   # require_shop_feature, IsShopStaff
│   │   ├── shops/               # Tenant management & feature flags
│   │   │   └── models.py        # Shop model with boolean feature toggles
│   │   ├── users/               # Custom user model, auth & roles (Cashier, Owner)
│   │   ├── inventory/           # Products, Categories, Stock tracking
│   │   ├── pos/                 # Checkout, Cart, Sales, Invoicing
│   │   ├── credit/              # Optional module: Customer ledger, Pay-later
│   │   ├── cheques/             # Optional module: Cheque clearance, deposits
│   │   └── notifications/       # Optional module: WhatsApp & Email integrations
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── src/
│       ├── api/                 # Axios/Fetch client with auth interceptors
│       ├── components/          # Reusable UI primitives (Buttons, Modals, Tables)
│       ├── context/             # AuthContext, ShopContext
│       ├── features/            # Modular feature domains (pos, inventory, credit)
│       ├── hooks/               # useFeatureFlag, useAuth, useDebounce
│       ├── types/               # TypeScript interfaces matching backend models
│       └── App.tsx
├── docs/                        # Architecture diagrams, API specs, database schemas
├── .gitignore                   # Monorepo ignore configuration
└── ARCHITECTURE.md              # THIS FILE (System rules & AI directives)
```

---

## 8. AI Assistant Self-Verification Checklist

Before submitting code suggestions or changes, the AI coding assistant must verify:

- [ ] **Multi-Tenancy:** Does every new business model inherit from `ShopAwareModel`?
- [ ] **Query Filtering:** Does `get_queryset()` strictly filter by `self.request.user.shop`?
- [ ] **Creation Safety:** Does `perform_create()` or serializer save assign `shop=request.user.shop` instead of trusting input data?
- [ ] **IDOR Protection:** Are related foreign keys (e.g., customer, product) validated to ensure they belong to the user's shop?
- [ ] **Modularity:** If introducing a feature (Credit, Cheques, WhatsApp, etc.), is it guarded by a boolean feature flag on `Shop`?
- [ ] **Permissions:** Is the endpoint protected by `require_shop_feature(...)`?
- [ ] **Frontend Check:** Is the UI element conditionally rendered using `useFeatureFlag(...)`?
- [ ] **Financial Safety:** Are stock updates and checkout processes wrapped in `transaction.atomic()` with appropriate concurrency locking?
- [ ] **Pedagogical Comments:** Are there comments explaining **WHY** key decisions and safety checks were implemented?
