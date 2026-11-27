/**
 * TypeScript Data Contracts for Modulr ERP + POS SaaS
 * Strictly aligned with Stage 1 Django REST Framework serializers.
 */

export type UserRole =
  | 'OWNER'
  | 'MANAGER'
  | 'CASHIER'
  | 'INVENTORY_MANAGER'
  | 'ACCOUNTANT';

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface UserProfile {
  id: number;
  public_id?: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  must_change_password?: boolean;
  is_owner?: boolean;
  is_cashier?: boolean;
}

export interface ShopFeatures {
  enable_credit_module: boolean;
  enable_whatsapp_alerts: boolean;
}

export interface ShopProfile {
  id: number;
  public_id: string;
  name: string;
  address: string;
  phone: string;
  is_active?: boolean;
  features: ShopFeatures;
}

export type TaxMode = 'NONE' | 'INCLUSIVE' | 'EXCLUSIVE';

export interface ShopSettings {
  managers_can_edit_products: boolean;
  managers_can_view_cost_price: boolean;
  managers_can_view_profit: boolean;
  managers_can_manage_purchasing: boolean;
  managers_can_manage_cashiers: boolean;
  cashier_max_discount_pct: string;
  tax_mode: TaxMode;
  tax_rate_pct: string;
  tax_label: string;
}

export interface Category {
  id: number;
  public_id: string;
  name: string;
  description: string;
  product_count?: number;
}

export interface Product {
  id: number;
  public_id: string;
  category: number | null;
  category_name: string | null;
  name: string;
  barcode: string | null;
  cost_price?: string; // Absent when user lacks inventory.view_cost_price
  selling_price: string;
  stock_quantity: string;
  reorder_level: string;
  is_low_stock: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Customer {
  id: number;
  public_id: string;
  name: string;
  phone: string;
  address?: string;
  total_credit_balance: string;
}

export interface InvoiceItemResponse {
  id: number;
  product: number;
  product_name: string;
  quantity: string;
  unit_price: string;
  cost_price_at_sale?: string;
  line_total: string;
}

export type PaymentMethod = 'CASH' | 'CARD' | 'CREDIT' | 'MIXED';
export type InvoiceStatus = 'COMPLETED' | 'VOIDED' | 'PARTIALLY_RETURNED' | 'RETURNED';

export interface SalesReturnItemResponse {
  id: number;
  public_id: string;
  product: number;
  product_name: string;
  invoice_item: number;
  quantity: string;
  unit_price: string;
  cost_price_at_sale?: string;
  line_total: string;
}

export interface SalesReturnResponse {
  id: number;
  public_id: string;
  return_number: string;
  invoice: number;
  invoice_number: string;
  reason: string;
  total_refund_amount: string;
  credit_reversed: string;
  cash_refunded: string;
  processed_by: number | null;
  processed_by_name?: string;
  items: SalesReturnItemResponse[];
  created_at: string;
}

export interface InvoiceResponse {
  id: number;
  public_id: string;
  invoice_number: string;
  status: InvoiceStatus;
  status_display?: string;
  customer?: number | null;
  customer_name?: string;
  customer_phone?: string;
  cashier?: number;
  cashier_name?: string;
  subtotal: string;
  discount: string;
  tax_mode: TaxMode;
  tax_rate_pct: string;
  tax_label: string;
  tax_amount: string;
  total_amount: string;
  payment_method: PaymentMethod;
  amount_paid: string;
  credit_amount: string;
  notes?: string;
  void_reason?: string | null;
  voided_at?: string | null;
  voided_by?: number | null;
  items: InvoiceItemResponse[];
  returns?: SalesReturnResponse[];
  whatsapp_share_url: string;
  created_at: string;
  updated_at?: string;
}

export interface SalesReturnCreatePayload {
  reason: string;
  items: {
    invoice_item_id: number;
    quantity: string;
  }[];
}

export interface DashboardOperationalSection {
  today_sales_total: string | number;
  today_invoice_count: number;
  sales_per_cashier_today: {
    cashier__username: string | null;
    invoice_count: number;
    total_sales: string | number;
  }[];
  low_stock_count: number;
  today_voided_count: number;
  today_discounted_count: number;
}

export interface DashboardProfitSection {
  today_gross_profit: string | number;
  thirty_day_gross_profit: string | number;
}

export interface DashboardCashierSection {
  my_sales_today_count: number;
  my_sales_today_total: string | number;
}

export interface DashboardInventorySection {
  low_stock_count: number;
  low_stock_items: {
    public_id: string;
    name: string;
    stock_quantity: string;
    reorder_level: string;
  }[];
  recent_stock_movements: {
    public_id: string;
    product__name: string;
    movement_type: string;
    quantity_change: string;
    balance_after: string;
    created_at: string;
  }[];
  top_moving_items: {
    product__public_id: string;
    product__name: string;
    units_sold: string;
  }[];
}

export interface DashboardFinanceSection {
  today_sales_total: string | number;
  thirty_day_sales_total: string | number;
  today_cash_collected: string | number;
  total_tax_collected: string | number;
  today_credit_issued?: string | number;
  outstanding_credit_total?: string | number;
  upcoming_cheques_7d_count?: number;
}

export interface DashboardSummaryResponse {
  operational?: DashboardOperationalSection;
  profit?: DashboardProfitSection;
  cashier?: DashboardCashierSection;
  inventory?: DashboardInventorySection;
  finance?: DashboardFinanceSection;
}

export interface CartItem {
  product: Product;
  quantity: string; // Precision decimal string like "0.250"
  unitPrice: string;
  lineTotal: string;
}

export interface CheckoutPayload {
  customer?: number | null;
  payment_method: PaymentMethod;
  discount: string;
  amount_paid: string;
  notes?: string;
  items: {
    product_id: number;
    quantity: string;
  }[];
}

export interface LoginResponse {
  access: string;
  user: UserProfile;
  shop: ShopProfile | null;
  permissions: string[];
  must_change_password: boolean;
}

export interface MeResponse extends UserProfile {
  shop: (Omit<ShopProfile, 'features'> & {
    enable_credit_module?: boolean;
    enable_whatsapp_alerts?: boolean;
    features?: ShopFeatures;
  }) | null;
  permissions: string[];
  must_change_password: boolean;
}

export interface RegisterShopPayload {
  shop_name: string;
  address?: string;
  phone?: string;
  username: string;
  email?: string;
  password: string;
  first_name?: string;
  last_name?: string;
}
