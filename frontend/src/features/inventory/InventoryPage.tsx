import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  AlertCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  FolderPlus,
  Package,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Tag,
  Upload,
  X,
} from 'lucide-react';
import {
  createCategory,
  createProduct,
  getCategories,
  getProducts,
  type CreateProductPayload,
} from '../../api/inventory';
import { Can } from '../../components/Can';
import { usePermission } from '../../hooks/usePermission';
import { formatLKR, formatMoneyFixed, formatQuantityFixed } from '../../lib/money';
import type { Category, Product } from '../../types/erp';
import { CsvImportModal } from './CsvImportModal';

export const InventoryPage: React.FC = () => {
  const canManageProducts = usePermission('inventory.manage_products');
  const canViewCostPrice = usePermission('inventory.view_cost_price');
  const [isCsvModalOpen, setIsCsvModalOpen] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Data & Pagination State
  // ---------------------------------------------------------------------------
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [page, setPage] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [hasNext, setHasNext] = useState<boolean>(false);
  const [hasPrevious, setHasPrevious] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Filter & Search State
  // ---------------------------------------------------------------------------
  const [search, setSearch] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [lowStockOnly, setLowStockOnly] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Add Product Modal State
  // ---------------------------------------------------------------------------
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const [newProduct, setNewProduct] = useState({
    name: '',
    barcode: '',
    category: '',
    cost_price: '0.00',
    selling_price: '',
    stock_quantity: '0.000',
    reorder_level: '5.000',
  });

  // ---------------------------------------------------------------------------
  // Inline Category Creation State
  // ---------------------------------------------------------------------------
  const [isCreatingCategory, setIsCreatingCategory] = useState<boolean>(false);
  const [newCategoryName, setNewCategoryName] = useState<string>('');
  const [categoryError, setCategoryError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Data Fetching
  // ---------------------------------------------------------------------------
  const fetchProducts = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const data = await getProducts({
        page,
        search: search.trim() || undefined,
        category: selectedCategory || undefined,
        low_stock: lowStockOnly ? true : undefined,
      });

      setProducts(data.results);
      setTotalCount(data.count);
      setHasNext(Boolean(data.next));
      setHasPrevious(Boolean(data.previous));
    } catch {
      setError('Failed to fetch inventory items. Please check connection.');
    } finally {
      setIsLoading(false);
    }
  }, [page, search, selectedCategory, lowStockOnly]);

  const fetchCategories = useCallback(async () => {
    try {
      const data = await getCategories(100);
      setCategories(data.results);
    } catch {
      // Ignore category fetch error silently
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchCategories();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchCategories]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchProducts();
    }, 250);
    return () => clearTimeout(timer);
  }, [fetchProducts]);

  // ---------------------------------------------------------------------------
  // Add Product Submit
  // ---------------------------------------------------------------------------
  const handleAddProductSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    if (!newProduct.name.trim() || !newProduct.selling_price) {
      setModalError('Product name and selling price are required.');
      return;
    }

    const payload: CreateProductPayload = {
      name: newProduct.name.trim(),
      barcode: newProduct.barcode.trim() || null,
      category: newProduct.category ? parseInt(newProduct.category, 10) : null,
      selling_price: formatMoneyFixed(newProduct.selling_price),
      stock_quantity: formatQuantityFixed(newProduct.stock_quantity || '0'),
      reorder_level: formatQuantityFixed(newProduct.reorder_level || '5'),
    };

    if (canViewCostPrice) {
      payload.cost_price = formatMoneyFixed(newProduct.cost_price || '0');
    }

    try {
      setIsSubmitting(true);
      await createProduct(payload);
      setIsAddModalOpen(false);
      setNewProduct({
        name: '',
        barcode: '',
        category: '',
        cost_price: '0.00',
        selling_price: '',
        stock_quantity: '0.000',
        reorder_level: '5.000',
      });
      fetchProducts();
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as Record<string, string | string[]> | undefined;
        if (data) {
          const firstKey = Object.keys(data)[0];
          const val = data[firstKey];
          setModalError(`${firstKey}: ${Array.isArray(val) ? val[0] : val}`);
        } else {
          setModalError('Failed to create product. Check input values.');
        }
      } else {
        setModalError('An unexpected error occurred.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Inline Category Submit
  // ---------------------------------------------------------------------------
  const handleCreateCategory = async () => {
    setCategoryError(null);
    if (!newCategoryName.trim()) {
      setCategoryError('Category name is required.');
      return;
    }

    try {
      const created = await createCategory({
        name: newCategoryName.trim(),
      });
      setCategories((prev) => [...prev, created]);
      setNewProduct((prev) => ({ ...prev, category: created.id.toString() }));
      setNewCategoryName('');
      setIsCreatingCategory(false);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as { name?: string[] } | undefined;
        setCategoryError(data?.name?.[0] || 'Category creation failed.');
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* -------------------------------------------------------------------- */}
      {/* Header Actions & Filter Controls                                    */}
      {/* -------------------------------------------------------------------- */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            Inventory & Stock
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage product pricing, barcodes, categories, and stock reorder alerts
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Can permission="inventory.csv_import">
            <button
              type="button"
              onClick={() => setIsCsvModalOpen(true)}
              className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-700 shadow-sm hover:bg-slate-50 transition-colors cursor-pointer"
            >
              <Upload className="h-4 w-4" />
              <span>Import CSV</span>
            </button>
          </Can>

          {canManageProducts && (
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-indigo-700 transition-colors cursor-pointer"
            >
              <Plus className="h-4 w-4" />
              <span>Add Product</span>
            </button>
          )}
        </div>
      </div>

      <CsvImportModal
        isOpen={isCsvModalOpen}
        onClose={() => setIsCsvModalOpen(false)}
        onSuccess={() => {
          fetchProducts();
          fetchCategories();
        }}
      />

      {/* Filter Toolbar */}
      <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-sm flex flex-col sm:flex-row gap-3">
        {/* Search Input */}
        <div className="relative flex-1">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
            <Search className="h-4 w-4" />
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search by product name or barcode..."
            className="block w-full rounded-lg border border-slate-300 pl-10 pr-4 py-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
          />
        </div>

        {/* Category Filter */}
        <div className="sm:w-56">
          <select
            value={selectedCategory}
            onChange={(e) => {
              setSelectedCategory(e.target.value);
              setPage(1);
            }}
            className="block w-full rounded-lg border border-slate-300 py-2 px-3 text-xs text-slate-700 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 bg-white"
          >
            <option value="">All Categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {/* Low Stock Toggle Button */}
        <button
          type="button"
          onClick={() => {
            setLowStockOnly((prev) => !prev);
            setPage(1);
          }}
          className={`flex items-center justify-center gap-1.5 rounded-lg border py-2 px-3.5 text-xs font-semibold transition-colors shrink-0 ${
            lowStockOnly
              ? 'border-amber-400 bg-amber-50 text-amber-800'
              : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
          <span>Low Stock Only</span>
        </button>

        {/* Refresh Button */}
        <button
          onClick={fetchProducts}
          title="Reload Inventory"
          className="rounded-lg border border-slate-300 bg-white p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-700 shrink-0"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* Products Table                                                       */}
      {/* -------------------------------------------------------------------- */}
      <div className="rounded-xl border border-slate-200/90 bg-white shadow-sm overflow-hidden">
        {error && (
          <div className="p-4 bg-red-50 text-red-700 text-xs font-medium flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs divide-y divide-slate-100">
            <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
              <tr>
                <th className="py-3 pl-4 pr-3">Product Name</th>
                <th className="py-3 px-3">Category</th>
                <th className="py-3 px-3">Barcode</th>
                {canViewCostPrice && (
                  <th className="py-3 px-3 text-right">
                    <span className="inline-flex items-center gap-1 text-purple-700" title="Restricted by inventory.view_cost_price permission">
                      <Shield className="h-3 w-3" /> Cost Price
                    </span>
                  </th>
                )}
                <th className="py-3 px-3 text-right">Selling Price</th>
                <th className="py-3 px-3 text-center">Available Stock</th>
                <th className="py-3 pr-4 pl-3 text-center">Status</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100 font-medium">
              {isLoading && products.length === 0 ? (
                <tr>
                  <td colSpan={canViewCostPrice ? 7 : 6} className="py-12 text-center text-slate-400">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
                      <span>Loading products...</span>
                    </div>
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={canViewCostPrice ? 7 : 6} className="py-12 text-center text-slate-400">
                    <Package className="h-8 w-8 mx-auto text-slate-300 stroke-[1.5]" />
                    <p className="mt-2 text-sm font-semibold text-slate-700">No products found</p>
                    <p className="text-xs text-slate-400">
                      Try adjusting your search criteria or add new inventory
                    </p>
                  </td>
                </tr>
              ) : (
                products.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="py-3.5 pl-4 pr-3">
                      <div className="font-bold text-slate-900">{p.name}</div>
                    </td>
                    <td className="py-3.5 px-3 text-slate-600">
                      {p.category_name ? (
                        <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700 font-semibold">
                          <Tag className="h-2.5 w-2.5" />
                          {p.category_name}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic text-[11px]">Uncategorized</span>
                      )}
                    </td>
                    <td className="py-3.5 px-3 font-mono text-[11px] text-slate-600">
                      {p.barcode || <span className="text-slate-300">—</span>}
                    </td>
                    {canViewCostPrice && (
                      <td className="py-3.5 px-3 text-right text-purple-700 font-semibold">
                        {formatLKR(p.cost_price ?? '0')}
                      </td>
                    )}
                    <td className="py-3.5 px-3 text-right font-bold text-slate-900">
                      {formatLKR(p.selling_price)}
                    </td>
                    <td className="py-3.5 px-3 text-center">
                      <span className="font-bold text-slate-800">{p.stock_quantity}</span>
                      <span className="text-[10px] text-slate-400 ml-1">/ min {p.reorder_level}</span>
                    </td>
                    <td className="py-3.5 pr-4 pl-3 text-center">
                      {p.is_low_stock ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-[10px] font-bold text-amber-700 border border-amber-200">
                          <AlertTriangle className="h-3 w-3 text-amber-500" /> Low Stock
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                          In Stock
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600">
          <span>
            Showing <span className="font-semibold text-slate-800">{products.length}</span> of{' '}
            <span className="font-semibold text-slate-800">{totalCount}</span> products (Page {page})
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!hasPrevious || isLoading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>Previous</span>
            </button>
            <button
              type="button"
              disabled={!hasNext || isLoading}
              onClick={() => setPage((p) => p + 1)}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>Next</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* ADD PRODUCT MODAL                                                    */}
      {/* -------------------------------------------------------------------- */}
      {isAddModalOpen && canManageProducts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto">
            <button
              onClick={() => setIsAddModalOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600"
            >
              <X className="h-5 w-5" />
            </button>

            <h3 className="text-lg font-bold text-slate-900 mb-1">Add New Product</h3>
            <p className="text-xs text-slate-500 mb-4">
              Enter product specifications for inventory cataloging and POS barcode checkout
            </p>

            {modalError && (
              <div className="mb-4 rounded-lg bg-red-50 p-3 text-xs font-semibold text-red-700 border border-red-200 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{modalError}</span>
              </div>
            )}

            <form onSubmit={handleAddProductSubmit} className="space-y-4 text-xs font-medium">
              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Product Name *
                </label>
                <input
                  type="text"
                  required
                  value={newProduct.name}
                  onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
                  placeholder="e.g. Ceylon Black Tea 500g"
                  className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Barcode / EAN (Optional)
                </label>
                <input
                  type="text"
                  value={newProduct.barcode}
                  onChange={(e) => setNewProduct({ ...newProduct, barcode: e.target.value })}
                  placeholder="e.g. 4791234567890"
                  className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 font-mono"
                />
              </div>

              {/* Category Selection + Inline Category Creator */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-slate-700 font-bold uppercase tracking-wider">
                    Category (Optional)
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsCreatingCategory((prev) => !prev)}
                    className="text-[11px] font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
                  >
                    <FolderPlus className="h-3 w-3" />
                    <span>{isCreatingCategory ? 'Cancel' : '+ New Category'}</span>
                  </button>
                </div>

                {isCreatingCategory ? (
                  <div className="flex gap-2 mb-2 p-2.5 bg-indigo-50/50 rounded-lg border border-indigo-100">
                    <input
                      type="text"
                      value={newCategoryName}
                      onChange={(e) => setNewCategoryName(e.target.value)}
                      placeholder="Category name (e.g. Beverages)"
                      className="flex-1 rounded border border-indigo-200 px-2 py-1 text-xs text-slate-900 bg-white"
                    />
                    <button
                      type="button"
                      onClick={handleCreateCategory}
                      className="rounded bg-indigo-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-indigo-700"
                    >
                      Create
                    </button>
                  </div>
                ) : null}

                {categoryError && (
                  <p className="text-[11px] text-red-600 mb-1.5">{categoryError}</p>
                )}

                <select
                  value={newProduct.category}
                  onChange={(e) => setNewProduct({ ...newProduct, category: e.target.value })}
                  className="block w-full rounded-lg border border-slate-300 py-2 px-3 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 bg-white"
                >
                  <option value="">-- No Category --</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Pricing Section */}
              <div className="grid grid-cols-2 gap-3">
                {canViewCostPrice && (
                  <div>
                    <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                      Cost Price (LKR)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={newProduct.cost_price}
                      onChange={(e) => setNewProduct({ ...newProduct, cost_price: e.target.value })}
                      placeholder="0.00"
                      className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                    />
                  </div>
                )}

                <div className={canViewCostPrice ? '' : 'col-span-2'}>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Selling Price (LKR) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    value={newProduct.selling_price}
                    onChange={(e) => setNewProduct({ ...newProduct, selling_price: e.target.value })}
                    placeholder="0.00"
                    className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 font-semibold"
                  />
                </div>
              </div>

              {/* Quantities (Decimal precision) */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Initial Stock Qty
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    value={newProduct.stock_quantity}
                    onChange={(e) => setNewProduct({ ...newProduct, stock_quantity: e.target.value })}
                    className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Reorder Alert Level
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    value={newProduct.reorder_level}
                    onChange={(e) => setNewProduct({ ...newProduct, reorder_level: e.target.value })}
                    className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                  />
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  {isSubmitting ? 'Saving...' : 'Save Product'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
