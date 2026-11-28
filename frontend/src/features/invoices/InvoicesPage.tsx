import React, { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileText,
  RefreshCw,
  Search,
} from 'lucide-react';
import { formatLKR } from '../../lib/money';
import type { InvoiceStatus, PaymentMethod } from '../../types/erp';
import { InvoiceDetailModal } from './InvoiceDetailModal';
import { getInvoices } from './invoices.api';

function getStatusBadgeClass(status: InvoiceStatus): string {
  switch (status) {
    case 'COMPLETED':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'VOIDED':
      return 'bg-red-50 text-red-700 border-red-200';
    case 'PARTIALLY_RETURNED':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'RETURNED':
      return 'bg-slate-100 text-slate-700 border-slate-300';
  }
}

export const InvoicesPage: React.FC = () => {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | ''>('');
  const [paymentFilter, setPaymentFilter] = useState<PaymentMethod | ''>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const [selectedPublicId, setSelectedPublicId] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: [
      'invoices',
      {
        page,
        search: debouncedSearch,
        status: statusFilter,
        paymentMethod: paymentFilter,
        dateFrom,
        dateTo,
      },
    ],
    queryFn: () =>
      getInvoices({
        page,
        search: debouncedSearch || undefined,
        status: statusFilter || undefined,
        payment_method: paymentFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
  });

  const invoices = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasNext = Boolean(data?.next);
  const hasPrevious = Boolean(data?.previous);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            Invoices &amp; Sales History
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Search receipts, reprint thermal bills, process voids and returns
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

      {/* Filter Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="relative lg:col-span-2">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-slate-400">
            <Search className="h-4 w-4" />
          </div>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => {
              setSearchInput(e.target.value);
              setPage(1);
            }}
            placeholder="Search invoice # or customer..."
            className="block w-full min-h-[44px] rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
          />
        </div>

        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as InvoiceStatus | '');
            setPage(1);
          }}
          className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-xs sm:text-sm text-slate-700 bg-white focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
        >
          <option value="">All Statuses</option>
          <option value="COMPLETED">Completed</option>
          <option value="VOIDED">Voided</option>
          <option value="PARTIALLY_RETURNED">Partially Returned</option>
          <option value="RETURNED">Returned</option>
        </select>

        <select
          aria-label="Filter by payment method"
          value={paymentFilter}
          onChange={(e) => {
            setPaymentFilter(e.target.value as PaymentMethod | '');
            setPage(1);
          }}
          className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-xs sm:text-sm text-slate-700 bg-white focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
        >
          <option value="">All Payment Methods</option>
          <option value="CASH">Cash</option>
          <option value="CARD">Card</option>
          <option value="CREDIT">Credit</option>
          <option value="MIXED">Mixed</option>
        </select>

        <div className="grid grid-cols-2 gap-2">
          <input
            type="date"
            aria-label="Date from"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value);
              setPage(1);
            }}
            className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-2 py-2 text-xs text-slate-700 focus:border-indigo-600 focus:outline-none"
          />
          <input
            type="date"
            aria-label="Date to"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              setPage(1);
            }}
            className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-2 py-2 text-xs text-slate-700 focus:border-indigo-600 focus:outline-none"
          />
        </div>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs sm:text-sm font-medium text-red-700 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>Failed to load invoices. Please try again.</span>
        </div>
      )}

      {/* Results Container */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading && invoices.length === 0 ? (
          <div className="py-12 flex flex-col items-center gap-2 text-slate-400">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
            <span className="text-xs">Loading invoices...</span>
          </div>
        ) : invoices.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <FileText className="h-8 w-8 mx-auto text-slate-300 stroke-[1.5]" />
            <p className="mt-2 text-sm font-semibold text-slate-700">No invoices found</p>
            <p className="text-xs text-slate-400">Try adjusting your search or date filters</p>
          </div>
        ) : (
          <>
            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left text-xs divide-y divide-slate-100">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="py-3 pl-4 pr-3">Invoice #</th>
                    <th className="py-3 px-3">Date</th>
                    <th className="py-3 px-3">Customer</th>
                    <th className="py-3 px-3">Cashier</th>
                    <th className="py-3 px-3 text-center">Payment</th>
                    <th className="py-3 px-3 text-center">Status</th>
                    <th className="py-3 px-3 text-right">Total</th>
                    <th className="py-3 pr-4 pl-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {invoices.map((inv) => (
                    <tr key={inv.public_id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 pl-4 pr-3 font-bold text-indigo-700">
                        {inv.invoice_number}
                      </td>
                      <td className="py-3 px-3 text-slate-500">
                        {new Date(inv.created_at).toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-slate-800">
                        {inv.customer_name || 'Walk-in Customer'}
                      </td>
                      <td className="py-3 px-3 text-slate-600">{inv.cashier_name || '—'}</td>
                      <td className="py-3 px-3 text-center">
                        <span className="inline-flex rounded bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-700">
                          {inv.payment_method}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span
                          className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getStatusBadgeClass(
                            inv.status
                          )}`}
                        >
                          {inv.status_display || inv.status}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-slate-900">
                        {formatLKR(inv.total_amount)}
                      </td>
                      <td className="py-3 pr-4 pl-3 text-right">
                        <button
                          type="button"
                          onClick={() => setSelectedPublicId(inv.public_id)}
                          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200 cursor-pointer"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          <span>View</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile / Tablet Stacked Cards */}
            <div className="md:hidden divide-y divide-slate-100">
              {invoices.map((inv) => (
                <div key={inv.public_id} className="p-4 space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-indigo-700">{inv.invoice_number}</p>
                      <p className="text-xs text-slate-500">
                        {new Date(inv.created_at).toLocaleString()}
                      </p>
                    </div>
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getStatusBadgeClass(
                        inv.status
                      )}`}
                    >
                      {inv.status_display || inv.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs text-slate-600">
                    <span>{inv.customer_name || 'Walk-in Customer'}</span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-700">
                      {inv.payment_method}
                    </span>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-base font-black text-slate-900">
                      {formatLKR(inv.total_amount)}
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedPublicId(inv.public_id)}
                      className="inline-flex min-h-[44px] items-center gap-1.5 rounded-xl bg-indigo-50 px-4 py-2 text-xs font-bold text-indigo-700 hover:bg-indigo-100 cursor-pointer"
                    >
                      <Eye className="h-4 w-4" />
                      <span>Details &amp; Reprint</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Pagination Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600">
          <span>
            Showing <span className="font-semibold text-slate-800">{invoices.length}</span> of{' '}
            <span className="font-semibold text-slate-800">{totalCount}</span> invoices (Page {page})
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!hasPrevious || isLoading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="h-4 w-4" />
              <span>Previous</span>
            </button>
            <button
              type="button"
              disabled={!hasNext || isLoading}
              onClick={() => setPage((p) => p + 1)}
              className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Next</span>
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Invoice Detail / Reprint / Void / Return Modal */}
      <InvoiceDetailModal
        publicId={selectedPublicId}
        onClose={() => setSelectedPublicId(null)}
      />
    </div>
  );
};
