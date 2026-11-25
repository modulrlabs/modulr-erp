import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  AlertCircle,
  Barcode,
  CheckCircle,
  CreditCard,
  DollarSign,
  Minus,
  Plus,
  Printer,
  RotateCcw,
  Search,
  Send,
  ShoppingCart,
  Trash2,
  UserCheck,
  X,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuthStore } from '../../stores/authStore';
import type {
  CartItem,
  CheckoutPayload,
  Customer,
  InvoiceResponse,
  PaymentMethod,
  Product,
} from '../../types/erp';

export const PosCheckoutPage: React.FC = () => {
  const { shop } = useAuthStore();

  // ---------------------------------------------------------------------------
  // Cart State
  // ---------------------------------------------------------------------------
  const [cart, setCart] = useState<CartItem[]>([]);
  const [discount, setDiscount] = useState<string>('0.00');
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('CASH');
  const [amountPaid, setAmountPaid] = useState<string>('');
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  const [notes, setNotes] = useState<string>('');

  // ---------------------------------------------------------------------------
  // Barcode & Product Search State
  // ---------------------------------------------------------------------------
  const [barcodeInput, setBarcodeInput] = useState<string>('');
  const [barcodeError, setBarcodeError] = useState<string | null>(null);
  const barcodeRef = useRef<HTMLInputElement>(null);

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchResults, setSearchResults] = useState<Product[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Customers List (for Credit / Mixed)
  // ---------------------------------------------------------------------------
  const [customers, setCustomers] = useState<Customer[]>([]);

  // ---------------------------------------------------------------------------
  // Checkout & Receipt State
  // ---------------------------------------------------------------------------
  const [isCheckingOut, setIsCheckingOut] = useState<boolean>(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [createdInvoice, setCreatedInvoice] = useState<InvoiceResponse | null>(null);

  // Auto-focus barcode scanner input on mount
  useEffect(() => {
    barcodeRef.current?.focus();
  }, []);

  // Fetch customers if credit module is enabled
  useEffect(() => {
    if (shop?.features.enable_credit_module) {
      apiClient
        .get<Customer[]>('/sales/customers/')
        .then((res) => setCustomers(res.data))
        .catch(() => {});
    }
  }, [shop?.features.enable_credit_module]);

  // Debounced product search
  useEffect(() => {
    if (!searchQuery.trim()) {
      return;
    }

    const timer = setTimeout(async () => {
      try {
        setIsSearching(true);
        const res = await apiClient.get<Product[]>(`/inventory/products/?search=${encodeURIComponent(searchQuery.trim())}`);
        setSearchResults(res.data);
      } catch {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  // ---------------------------------------------------------------------------
  // Cart Actions
  // ---------------------------------------------------------------------------
  const addProductToCart = (product: Product, quantityToAdd: string = '1.000') => {
    setCart((prev) => {
      const existingIdx = prev.findIndex((item) => item.product.id === product.id);
      const unitPrice = parseFloat(product.selling_price) || 0;

      if (existingIdx >= 0) {
        const existing = prev[existingIdx];
        const newQty = (parseFloat(existing.quantity) + parseFloat(quantityToAdd)).toFixed(3);
        const newTotal = parseFloat(newQty) * unitPrice;
        const updated = [...prev];
        updated[existingIdx] = {
          ...existing,
          quantity: newQty,
          lineTotal: newTotal,
        };
        return updated;
      } else {
        const qtyNum = parseFloat(quantityToAdd) || 1;
        return [
          ...prev,
          {
            product,
            quantity: quantityToAdd,
            unitPrice,
            lineTotal: qtyNum * unitPrice,
          },
        ];
      }
    });

    setBarcodeError(null);
  };

  const updateQuantity = (productId: number, newQtyStr: string) => {
    setCart((prev) =>
      prev
        .map((item) => {
          if (item.product.id !== productId) return item;
          const num = parseFloat(newQtyStr);
          if (isNaN(num) || num <= 0) {
            return { ...item, quantity: newQtyStr, lineTotal: 0 };
          }
          return {
            ...item,
            quantity: newQtyStr,
            lineTotal: num * item.unitPrice,
          };
        })
        .filter((item) => parseFloat(item.quantity) > 0 || item.quantity === '')
    );
  };

  const removeCartItem = (productId: number) => {
    setCart((prev) => prev.filter((item) => item.product.id !== productId));
  };

  const clearCart = () => {
    setCart([]);
    setDiscount('0.00');
    setAmountPaid('');
    setNotes('');
    setCheckoutError(null);
    barcodeRef.current?.focus();
  };

  // ---------------------------------------------------------------------------
  // Barcode Scan Handler
  // ---------------------------------------------------------------------------
  const handleBarcodeScan = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = barcodeInput.trim();
    if (!code) return;

    setBarcodeError(null);
    try {
      const res = await apiClient.get<Product>(`/inventory/products/by-barcode/?code=${encodeURIComponent(code)}`);
      addProductToCart(res.data, '1.000');
      setBarcodeInput('');
    } catch (err: unknown) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        setBarcodeError(`No product found with barcode "${code}"`);
      } else {
        setBarcodeError('Failed to scan barcode. Please check connection.');
      }
    } finally {
      barcodeRef.current?.focus();
    }
  };

  // ---------------------------------------------------------------------------
  // Calculations
  // ---------------------------------------------------------------------------
  const subtotal = cart.reduce((sum, item) => sum + (item.lineTotal || 0), 0);
  const discountNum = Math.max(0, parseFloat(discount) || 0);
  const grandTotal = Math.max(0, subtotal - discountNum);

  const amountPaidNum = parseFloat(amountPaid) || 0;
  const isCashOrMixed = paymentMethod === 'CASH' || paymentMethod === 'MIXED';
  const effectivePaid =
    amountPaid.trim() === '' && (paymentMethod === 'CASH' || paymentMethod === 'CARD')
      ? grandTotal
      : amountPaidNum;

  const changeDue = Math.max(0, effectivePaid - grandTotal);
  const creditDebt = Math.max(0, grandTotal - effectivePaid);

  // ---------------------------------------------------------------------------
  // Atomic POS Checkout with Idempotency-Key
  // ---------------------------------------------------------------------------
  const handleCheckout = async () => {
    setCheckoutError(null);

    if (cart.length === 0) {
      setCheckoutError('Cart is empty. Scan or select products to checkout.');
      return;
    }

    if ((paymentMethod === 'CREDIT' || creditDebt > 0) && !selectedCustomerId) {
      setCheckoutError('A registered customer must be selected when issuing store credit / pay later.');
      return;
    }

    // Generate fresh UUIDv4 idempotency key for this checkout transaction
    const idempotencyKey = crypto.randomUUID();

    const payload: CheckoutPayload = {
      customer: selectedCustomerId,
      payment_method: paymentMethod,
      discount: discountNum.toFixed(2),
      amount_paid: effectivePaid.toFixed(2),
      notes: notes.trim(),
      items: cart.map((item) => ({
        product_id: item.product.id,
        quantity: parseFloat(item.quantity).toFixed(3),
      })),
    };

    try {
      setIsCheckingOut(true);
      const res = await apiClient.post<InvoiceResponse>('/sales/invoices/', payload, {
        headers: {
          'Idempotency-Key': idempotencyKey,
        },
      });

      setCreatedInvoice(res.data);
      clearCart();
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as { detail?: string; items?: string | string[] } | undefined;
        const msg =
          data?.detail ||
          (Array.isArray(data?.items) ? data.items[0] : data?.items) ||
          'Checkout failed. Please check product stock and amounts.';
        setCheckoutError(msg);
      } else {
        setCheckoutError('An unexpected error occurred during checkout.');
      }
    } finally {
      setIsCheckingOut(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      {/* -------------------------------------------------------------------- */}
      {/* LEFT COLUMN: Product Catalog & Barcode Scanner (7 cols)             */}
      {/* -------------------------------------------------------------------- */}
      <div className="lg:col-span-7 space-y-4">
        {/* Fast Scanner Input */}
        <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm">
          <form onSubmit={handleBarcodeScan} className="flex gap-2">
            <div className="relative flex-1">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-indigo-500">
                <Barcode className="h-5 w-5" />
              </div>
              <input
                ref={barcodeRef}
                type="text"
                value={barcodeInput}
                onChange={(e) => setBarcodeInput(e.target.value)}
                placeholder="Scan barcode or type and press Enter..."
                className="block w-full rounded-lg border-2 border-indigo-100 bg-indigo-50/20 pl-11 pr-4 py-2.5 text-sm font-medium text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
              />
            </div>
            <button
              type="submit"
              className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors cursor-pointer shrink-0"
            >
              Scan
            </button>
          </form>

          {barcodeError && (
            <div className="mt-2.5 flex items-center gap-2 text-xs font-semibold text-red-600 bg-red-50 p-2.5 rounded-lg border border-red-200">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{barcodeError}</span>
            </div>
          )}
        </div>

        {/* Live Search & Catalog Quick-Add */}
        <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm">
          <div className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
              <Search className="h-4 w-4" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                const val = e.target.value;
                setSearchQuery(val);
                if (!val.trim()) {
                  setSearchResults([]);
                }
              }}
              placeholder="Search products by name or barcode..."
              className="block w-full rounded-lg border border-slate-300 pl-10 pr-4 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
            />
          </div>

          {/* Search Results Dropdown / Grid */}
          {searchQuery && (
            <div className="mt-3 max-h-72 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100 bg-white">
              {isSearching ? (
                <div className="p-4 text-center text-xs text-slate-500">Searching inventory...</div>
              ) : searchResults.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-500">No products matched "{searchQuery}"</div>
              ) : (
                searchResults.map((product) => (
                  <div
                    key={product.id}
                    onClick={() => {
                      addProductToCart(product);
                      setSearchQuery('');
                      barcodeRef.current?.focus();
                    }}
                    className="flex items-center justify-between p-3 hover:bg-indigo-50/60 cursor-pointer transition-colors"
                  >
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{product.name}</div>
                      <div className="text-xs text-slate-500">
                        {product.category_name || 'Uncategorized'} • Barcode: {product.barcode || 'N/A'} • Available:{' '}
                        <span className={`font-semibold ${product.is_low_stock ? 'text-amber-600' : 'text-slate-700'}`}>
                          {product.stock_quantity}
                        </span>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-indigo-600">LKR {parseFloat(product.selling_price).toFixed(2)}</div>
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                        <Plus className="h-3 w-3" /> Add
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Current Cart Item Table */}
        <div className="rounded-xl border border-slate-200/90 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/70 px-4 py-3">
            <div className="flex items-center gap-2">
              <ShoppingCart className="h-4 w-4 text-slate-700" />
              <h3 className="text-sm font-bold text-slate-800">
                Cart Items ({cart.length})
              </h3>
            </div>
            {cart.length > 0 && (
              <button
                onClick={clearCart}
                className="flex items-center gap-1 text-xs font-semibold text-red-600 hover:text-red-700 transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Clear
              </button>
            )}
          </div>

          {cart.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <ShoppingCart className="h-10 w-10 mx-auto text-slate-300 stroke-[1.5]" />
              <p className="mt-2 text-sm font-medium">Cart is currently empty</p>
              <p className="text-xs">Scan a barcode or search products above to start billing</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm divide-y divide-slate-100">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="py-2.5 pl-4 pr-2">Product</th>
                    <th className="py-2.5 px-2 text-right">Price</th>
                    <th className="py-2.5 px-2 text-center w-36">Quantity</th>
                    <th className="py-2.5 px-2 text-right">Total</th>
                    <th className="py-2.5 pr-4 pl-2 w-10 text-center"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {cart.map((item) => (
                    <tr key={item.product.id} className="hover:bg-slate-50/50">
                      <td className="py-3 pl-4 pr-2">
                        <div className="font-semibold text-slate-900 leading-tight">{item.product.name}</div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          Stock: {item.product.stock_quantity}
                        </div>
                      </td>
                      <td className="py-3 px-2 text-right text-slate-600">
                        {item.unitPrice.toFixed(2)}
                      </td>
                      <td className="py-3 px-2">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              const curr = parseFloat(item.quantity) || 0;
                              if (curr > 1) {
                                updateQuantity(item.product.id, (curr - 1).toFixed(3));
                              }
                            }}
                            className="h-7 w-7 rounded bg-slate-100 flex items-center justify-center text-slate-600 hover:bg-slate-200"
                          >
                            <Minus className="h-3 w-3" />
                          </button>
                          <input
                            type="number"
                            step="0.001"
                            min="0.001"
                            value={item.quantity}
                            onChange={(e) => updateQuantity(item.product.id, e.target.value)}
                            className="w-16 rounded border border-slate-300 py-1 px-1.5 text-center text-xs font-semibold text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              const curr = parseFloat(item.quantity) || 0;
                              updateQuantity(item.product.id, (curr + 1).toFixed(3));
                            }}
                            className="h-7 w-7 rounded bg-slate-100 flex items-center justify-center text-slate-600 hover:bg-slate-200"
                          >
                            <Plus className="h-3 w-3" />
                          </button>
                        </div>
                      </td>
                      <td className="py-3 px-2 text-right font-bold text-slate-900">
                        {item.lineTotal.toFixed(2)}
                      </td>
                      <td className="py-3 pr-4 pl-2 text-center">
                        <button
                          onClick={() => removeCartItem(item.product.id)}
                          className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* RIGHT COLUMN: Bill Summary & Checkout Panel (5 cols)                */}
      {/* -------------------------------------------------------------------- */}
      <div className="lg:col-span-5 space-y-4">
        <div className="rounded-xl border border-slate-200/90 bg-white p-5 shadow-sm space-y-5">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 border-b border-slate-100 pb-2">
            Order Summary
          </h3>

          {/* Subtotal & Discount Inputs */}
          <div className="space-y-2.5 text-sm">
            <div className="flex justify-between text-slate-600">
              <span>Subtotal</span>
              <span className="font-semibold text-slate-900">LKR {subtotal.toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between gap-4">
              <label htmlFor="discount" className="text-slate-600 text-xs font-bold uppercase">
                Discount (LKR)
              </label>
              <input
                id="discount"
                type="number"
                min="0"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                className="w-28 rounded-lg border border-slate-300 py-1.5 px-3 text-right text-sm font-semibold text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
              />
            </div>

            <div className="border-t border-slate-100 pt-3 flex justify-between items-baseline">
              <span className="text-base font-bold text-slate-900">Grand Total</span>
              <span className="text-2xl font-black text-indigo-700">LKR {grandTotal.toFixed(2)}</span>
            </div>
          </div>

          {/* Payment Method Selector */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
              Payment Method
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(['CASH', 'CARD', 'CREDIT', 'MIXED'] as PaymentMethod[]).map((method) => {
                const isCreditDisabled =
                  (method === 'CREDIT' || method === 'MIXED') && !shop?.features.enable_credit_module;

                return (
                  <button
                    key={method}
                    type="button"
                    disabled={isCreditDisabled}
                    onClick={() => setPaymentMethod(method)}
                    className={`flex items-center justify-center gap-1.5 rounded-lg border py-2.5 px-3 text-xs font-bold transition-all ${
                      paymentMethod === method
                        ? 'border-indigo-600 bg-indigo-50 text-indigo-700 ring-2 ring-indigo-600/20'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                    } ${isCreditDisabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    {method === 'CASH' && <DollarSign className="h-3.5 w-3.5" />}
                    {method === 'CARD' && <CreditCard className="h-3.5 w-3.5" />}
                    {method === 'CREDIT' && <UserCheck className="h-3.5 w-3.5" />}
                    {method === 'MIXED' && <RotateCcw className="h-3.5 w-3.5" />}
                    <span>{method}</span>
                  </button>
                );
              })}
            </div>
            {!shop?.features.enable_credit_module && (
              <p className="mt-1.5 text-[11px] text-slate-400">
                Credit module is not active for this subscription tier.
              </p>
            )}
          </div>

          {/* Customer Selection (Required for CREDIT / optional for others) */}
          {(paymentMethod === 'CREDIT' || paymentMethod === 'MIXED' || shop?.features.enable_credit_module) && (
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                Customer {paymentMethod === 'CREDIT' || creditDebt > 0 ? '*' : '(Optional)'}
              </label>
              <select
                value={selectedCustomerId || ''}
                onChange={(e) => setSelectedCustomerId(e.target.value ? parseInt(e.target.value) : null)}
                className="block w-full rounded-lg border border-slate-300 py-2 px-3 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 bg-white"
              >
                <option value="">-- Select Customer / Pay Later Client --</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.phone || 'No phone'}) - Current Debt: LKR {parseFloat(c.total_credit_balance).toFixed(2)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Cash Tender & Change Calculations */}
          {isCashOrMixed && (
            <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-200/80 space-y-2.5">
              <div className="flex items-center justify-between gap-4">
                <label htmlFor="amountPaid" className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Cash Paid
                </label>
                <input
                  id="amountPaid"
                  type="number"
                  step="0.01"
                  min="0"
                  value={amountPaid}
                  onChange={(e) => setAmountPaid(e.target.value)}
                  placeholder={grandTotal.toFixed(2)}
                  className="w-32 rounded-lg border border-slate-300 py-1.5 px-3 text-right text-sm font-semibold text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 bg-white"
                />
              </div>

              {changeDue > 0 && (
                <div className="flex justify-between items-center text-xs font-bold text-emerald-700 pt-1 border-t border-slate-200/60">
                  <span>Change to Return</span>
                  <span className="text-base font-black">LKR {changeDue.toFixed(2)}</span>
                </div>
              )}

              {creditDebt > 0 && (
                <div className="flex justify-between items-center text-xs font-bold text-amber-700 pt-1 border-t border-slate-200/60">
                  <span>Balance Due (Store Credit)</span>
                  <span className="text-base font-black">LKR {creditDebt.toFixed(2)}</span>
                </div>
              )}
            </div>
          )}

          {/* Optional Invoice Notes */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
              Remarks / Notes
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Counter #1 walk-in sale"
              className="block w-full rounded-lg border border-slate-300 py-1.5 px-3 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
            />
          </div>

          {/* Checkout Error Banner */}
          {checkoutError && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-500 mt-0.5" />
              <span>{checkoutError}</span>
            </div>
          )}

          {/* Complete Checkout Button */}
          <button
            onClick={handleCheckout}
            disabled={isCheckingOut || cart.length === 0}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3.5 px-4 text-sm font-bold text-white shadow-md shadow-indigo-200 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2 disabled:opacity-50 transition-all cursor-pointer"
          >
            {isCheckingOut ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                <span>Processing Transaction...</span>
              </>
            ) : (
              <>
                <CheckCircle className="h-5 w-5" />
                <span>Charge LKR {grandTotal.toFixed(2)}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* RECEIPT MODAL                                                        */}
      {/* -------------------------------------------------------------------- */}
      {createdInvoice && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 max-h-[90vh] flex flex-col">
            <button
              onClick={() => setCreatedInvoice(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600"
            >
              <X className="h-5 w-5" />
            </button>

            {/* Printable Receipt Content */}
            <div id="printable-receipt" className="flex-1 overflow-y-auto pr-1 space-y-4">
              <div className="text-center border-b border-dashed border-slate-300 pb-3">
                <h4 className="text-lg font-black text-slate-900 tracking-tight">
                  {shop?.name || 'Modulr Store'}
                </h4>
                <p className="text-xs text-slate-500">{shop?.address || 'Retail Sales'}</p>
                <p className="text-xs text-slate-500">{shop?.phone || ''}</p>
                <div className="mt-2 inline-block rounded bg-indigo-50 px-2 py-0.5 text-xs font-bold text-indigo-700">
                  {createdInvoice.invoice_number}
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  {new Date(createdInvoice.created_at).toLocaleString()}
                </p>
              </div>

              {/* Items Summary */}
              <div className="space-y-1.5 text-xs">
                {createdInvoice.items.map((item) => (
                  <div key={item.id} className="flex justify-between py-1 border-b border-slate-100">
                    <div>
                      <span className="font-semibold text-slate-800">{item.product_name}</span>
                      <span className="text-slate-400 block text-[11px]">
                        {item.quantity} x {parseFloat(item.unit_price).toFixed(2)}
                      </span>
                    </div>
                    <span className="font-bold text-slate-900">
                      LKR {parseFloat(item.line_total).toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>

              {/* Financial Totals */}
              <div className="border-t border-slate-200 pt-2 space-y-1 text-xs">
                <div className="flex justify-between text-slate-600">
                  <span>Subtotal</span>
                  <span>LKR {parseFloat(createdInvoice.subtotal).toFixed(2)}</span>
                </div>
                {parseFloat(createdInvoice.discount) > 0 && (
                  <div className="flex justify-between text-slate-600">
                    <span>Discount</span>
                    <span>- LKR {parseFloat(createdInvoice.discount).toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm font-extrabold text-slate-900 pt-1 border-t border-dashed border-slate-300">
                  <span>Total Paid</span>
                  <span>LKR {parseFloat(createdInvoice.total_amount).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-[11px] text-slate-500">
                  <span>Method</span>
                  <span className="font-bold">{createdInvoice.payment_method}</span>
                </div>
                {parseFloat(createdInvoice.credit_amount) > 0 && (
                  <div className="flex justify-between text-xs font-bold text-amber-700">
                    <span>Store Credit Balance</span>
                    <span>LKR {parseFloat(createdInvoice.credit_amount).toFixed(2)}</span>
                  </div>
                )}
              </div>

              <div className="text-center text-[11px] text-slate-400 border-t border-dashed border-slate-300 pt-3">
                Thank you for shopping with us!
              </div>
            </div>

            {/* Action Buttons */}
            <div className="mt-4 pt-4 border-t border-slate-100 flex flex-col gap-2">
              <div className="flex gap-2">
                <button
                  onClick={() => window.print()}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-slate-300 bg-white py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 transition-colors shadow-sm cursor-pointer"
                >
                  <Printer className="h-4 w-4" /> Print Receipt
                </button>

                <a
                  href={createdInvoice.whatsapp_share_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition-colors shadow-sm text-center"
                >
                  <Send className="h-3.5 w-3.5" /> WhatsApp
                </a>
              </div>

              <button
                onClick={() => setCreatedInvoice(null)}
                className="w-full rounded-lg bg-indigo-600 py-2 text-xs font-bold text-white hover:bg-indigo-700 transition-colors cursor-pointer"
              >
                Start New Sale
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
