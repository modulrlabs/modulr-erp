import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  CalendarClock,
  CreditCard,
  Package,
  Receipt,
  RefreshCw,
  ShoppingCart,
  TrendingUp,
  Users,
} from 'lucide-react';
import { formatLKR, formatQuantityFixed, parseMoney } from '../../lib/money';
import { useAuthStore } from '../../stores/authStore';
import { getDashboardSummary } from './dashboard.api';

export const DashboardPage: React.FC = () => {
  const { user, shop } = useAuthStore();

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: getDashboardSummary,
  });

  const hasCreditMetrics =
    data?.finance !== undefined &&
    data.finance.outstanding_credit_total !== undefined &&
    data.finance.upcoming_cheques_7d_count !== undefined;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            {shop?.name ? `${shop.name} Overview` : 'Dashboard'}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Live metrics tailored to your role ({user?.role || 'Staff'})
          </p>
        </div>

        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs sm:text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 cursor-pointer shrink-0"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((n) => (
            <div
              key={n}
              className="h-28 animate-pulse rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="h-3 w-24 rounded bg-slate-200" />
              <div className="mt-4 h-7 w-32 rounded bg-slate-200" />
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {isError && !isLoading && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <span>Failed to load dashboard summary. Please try refreshing.</span>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className="min-h-[44px] rounded-lg bg-red-600 px-3 py-2 text-xs font-bold text-white hover:bg-red-700 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {/* 1. Cashier Personal Section */}
          {data.cashier && (
            <section className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50/80 to-white p-5 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-indigo-700">
                    My Sales Today
                  </h2>
                  <div className="flex flex-wrap items-baseline gap-4">
                    <span className="text-2xl sm:text-3xl font-black text-slate-900">
                      {formatLKR(data.cashier.my_sales_today_total)}
                    </span>
                    <span className="text-xs sm:text-sm font-semibold text-slate-600">
                      {data.cashier.my_sales_today_count} invoice
                      {data.cashier.my_sales_today_count === 1 ? '' : 's'} completed
                    </span>
                  </div>
                </div>

                <Link
                  to="/pos"
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 transition-colors shrink-0"
                >
                  <ShoppingCart className="h-4 w-4" />
                  <span>Open POS</span>
                </Link>
              </div>
            </section>
          )}

          {/* 2. Profit Section (highlighted cleanly) */}
          {data.profit && (
            <section className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Gross Profit
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-emerald-700">
                      Today&apos;s Gross Profit
                    </span>
                    <TrendingUp className="h-5 w-5 text-emerald-600" />
                  </div>
                  <p className="mt-2 text-2xl sm:text-3xl font-black text-slate-900">
                    {formatLKR(data.profit.today_gross_profit)}
                  </p>
                </div>

                <div className="rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50/60 to-white p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-emerald-700">
                      30-Day Net Gross Profit
                    </span>
                    <TrendingUp className="h-5 w-5 text-emerald-600" />
                  </div>
                  <p className="mt-2 text-2xl sm:text-3xl font-black text-slate-900">
                    {formatLKR(data.profit.thirty_day_gross_profit)}
                  </p>
                </div>
              </div>
            </section>
          )}

          {/* 3. Operational Section */}
          {data.operational && (
            <section className="space-y-4">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Today&apos;s Operations
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5">
                <div className="col-span-2 lg:col-span-1 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Today&apos;s Sales
                  </span>
                  <p className="mt-1.5 text-xl font-black text-indigo-700">
                    {formatLKR(data.operational.today_sales_total)}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Invoices
                  </span>
                  <p className="mt-1.5 text-xl font-black text-slate-900">
                    {data.operational.today_invoice_count}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Voided Today
                  </span>
                  <p className="mt-1.5 text-xl font-black text-red-600">
                    {data.operational.today_voided_count}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Discounted
                  </span>
                  <p className="mt-1.5 text-xl font-black text-slate-900">
                    {data.operational.today_discounted_count}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Low Stock Items
                  </span>
                  <p className="mt-1.5 text-xl font-black text-amber-600">
                    {data.operational.low_stock_count}
                  </p>
                </div>
              </div>

              {/* Sales by Cashier Today */}
              <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-3">
                  <Users className="h-4 w-4 text-slate-600" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Sales by Cashier Today
                  </h3>
                </div>
                {data.operational.sales_per_cashier_today.length === 0 ? (
                  <p className="p-4 text-xs text-slate-500">No completed sales recorded today yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs divide-y divide-slate-100">
                      <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                        <tr>
                          <th className="py-2.5 px-4">Cashier</th>
                          <th className="py-2.5 px-4 text-center">Invoices</th>
                          <th className="py-2.5 px-4 text-right">Total Sales</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {data.operational.sales_per_cashier_today.map((row, idx) => (
                          <tr key={row.cashier__username ?? `cashier-${idx}`}>
                            <td className="py-3 px-4 font-semibold text-slate-800">
                              {row.cashier__username || 'Unassigned'}
                            </td>
                            <td className="py-3 px-4 text-center text-slate-600">
                              {row.invoice_count}
                            </td>
                            <td className="py-3 px-4 text-right font-bold text-slate-900">
                              {formatLKR(row.total_sales)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* 4. Finance Section */}
          {data.finance && (
            <section className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Finance &amp; Tax
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-500">
                    <span className="text-[11px] font-bold uppercase tracking-wider">
                      Today&apos;s Sales
                    </span>
                    <Receipt className="h-4 w-4 text-indigo-600" />
                  </div>
                  <p className="mt-2 text-xl font-black text-slate-900">
                    {formatLKR(data.finance.today_sales_total)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    30d: {formatLKR(data.finance.thirty_day_sales_total)}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-500">
                    <span className="text-[11px] font-bold uppercase tracking-wider">
                      Cash Collected Today
                    </span>
                    <Banknote className="h-4 w-4 text-emerald-600" />
                  </div>
                  <p className="mt-2 text-xl font-black text-slate-900">
                    {formatLKR(data.finance.today_cash_collected)}
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between text-slate-500">
                    <span className="text-[11px] font-bold uppercase tracking-wider">
                      Tax Collected Today
                    </span>
                    <Receipt className="h-4 w-4 text-slate-600" />
                  </div>
                  <p className="mt-2 text-xl font-black text-slate-900">
                    {formatLKR(data.finance.total_tax_collected)}
                  </p>
                </div>

                {hasCreditMetrics && (
                  <>
                    <div className="rounded-xl border border-amber-200 bg-amber-50/40 p-4 shadow-sm">
                      <div className="flex items-center justify-between text-amber-800">
                        <span className="text-[11px] font-bold uppercase tracking-wider">
                          Outstanding Credit
                        </span>
                        <CreditCard className="h-4 w-4 text-amber-600" />
                      </div>
                      <p className="mt-2 text-xl font-black text-amber-900">
                        {formatLKR(data.finance.outstanding_credit_total)}
                      </p>
                      {data.finance.today_credit_issued !== undefined && (
                        <p className="mt-1 text-[11px] text-amber-700">
                          Issued today: {formatLKR(data.finance.today_credit_issued)}
                        </p>
                      )}
                    </div>

                    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                      <div className="flex items-center justify-between text-slate-500">
                        <span className="text-[11px] font-bold uppercase tracking-wider">
                          Upcoming Cheques (7d)
                        </span>
                        <CalendarClock className="h-4 w-4 text-indigo-600" />
                      </div>
                      <p className="mt-2 text-xl font-black text-slate-900">
                        {data.finance.upcoming_cheques_7d_count}
                      </p>
                    </div>
                  </>
                )}
              </div>
            </section>
          )}

          {/* 5. Inventory Section */}
          {data.inventory && (
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Inventory Insights
                </h2>
                <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-700 border border-amber-200">
                  {data.inventory.low_stock_count} Low Stock
                </span>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                {/* Low Stock Alerts */}
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-3">
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                      Low Stock Alerts (Top 10)
                    </h3>
                  </div>
                  {data.inventory.low_stock_items.length === 0 ? (
                    <p className="p-4 text-xs text-slate-500">All products are above reorder level.</p>
                  ) : (
                    <ul className="divide-y divide-slate-100 text-xs">
                      {data.inventory.low_stock_items.map((item) => (
                        <li
                          key={item.public_id}
                          className="flex items-center justify-between px-4 py-2.5"
                        >
                          <span className="font-semibold text-slate-800 truncate pr-2">
                            {item.name}
                          </span>
                          <span className="shrink-0 font-bold text-amber-700">
                            {formatQuantityFixed(item.stock_quantity)} / min{' '}
                            {formatQuantityFixed(item.reorder_level)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Top-Moving Items (30d) */}
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-3">
                    <Package className="h-4 w-4 text-indigo-600" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                      Top-Moving Items (30d)
                    </h3>
                  </div>
                  {data.inventory.top_moving_items.length === 0 ? (
                    <p className="p-4 text-xs text-slate-500">No item sales in the last 30 days.</p>
                  ) : (
                    <ul className="divide-y divide-slate-100 text-xs">
                      {data.inventory.top_moving_items.map((item) => (
                        <li
                          key={item.product__public_id}
                          className="flex items-center justify-between px-4 py-2.5"
                        >
                          <span className="font-semibold text-slate-800 truncate pr-2">
                            {item.product__name}
                          </span>
                          <span className="shrink-0 font-bold text-indigo-700">
                            {formatQuantityFixed(item.units_sold)} sold
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Recent Stock Movements */}
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-3">
                    <RefreshCw className="h-4 w-4 text-slate-600" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                      Recent Stock Movements
                    </h3>
                  </div>
                  {data.inventory.recent_stock_movements.length === 0 ? (
                    <p className="p-4 text-xs text-slate-500">No stock movements recorded yet.</p>
                  ) : (
                    <ul className="divide-y divide-slate-100 text-xs">
                      {data.inventory.recent_stock_movements.map((mv) => {
                        const qtyDec = parseMoney(mv.quantity_change);
                        const isPositive = qtyDec.gt(0);
                        return (
                          <li
                            key={mv.public_id}
                            className="flex items-center justify-between px-4 py-2.5 gap-2"
                          >
                            <div className="min-w-0">
                              <p className="font-semibold text-slate-800 truncate">
                                {mv.product__name}
                              </p>
                              <p className="text-[11px] text-slate-400">
                                {mv.movement_type} • Bal: {formatQuantityFixed(mv.balance_after)}
                              </p>
                            </div>
                            <span
                              className={`inline-flex items-center gap-0.5 shrink-0 font-bold ${
                                isPositive ? 'text-emerald-700' : 'text-red-600'
                              }`}
                            >
                              {isPositive ? (
                                <ArrowUpRight className="h-3.5 w-3.5" />
                              ) : (
                                <ArrowDownRight className="h-3.5 w-3.5" />
                              )}
                              {formatQuantityFixed(mv.quantity_change)}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
};
