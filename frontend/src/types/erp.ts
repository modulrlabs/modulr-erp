/**
 * TypeScript Data Contracts for Modulr ERP + POS SaaS
 * Strictly matching Django REST Framework serializers across core, inventory, and sales.
 */

export type UserRole = 'OWNER' | 'CASHIER';

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
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
  cost_price?: string; // Hidden from Cashiers by ProductSerializer
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
  total_amount: string;
  payment_method: PaymentMethod;
  amount_paid: string;
  credit_amount: string;
  notes?: string;
  items: InvoiceItemResponse[];
  whatsapp_share_url: string;
  created_at: string;
  updated_at?: string;
}

export interface CartItem {
  product: Product;
  quantity: string; // Stored as string to support precision decimal input like "0.250"
  unitPrice: number;
  lineTotal: number;
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
