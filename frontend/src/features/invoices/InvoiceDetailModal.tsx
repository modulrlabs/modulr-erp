import React, { useMemo, useState } from 'react';
import axios from 'axios';
import Decimal from 'decimal.js';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  Ban,
  Printer,
  RotateCcw,
  Send,
  X,
} from 'lucide-react';
import { Can } from '../../components/Can';
import {
  formatLKR,
  formatMoneyFixed,
  formatQuantityFixed,
  parseMoney,
  parseQuantity,
} from '../../lib/money';
import { useAuthStore } from '../../stores/authStore';
import type { InvoiceResponse, InvoiceStatus } from '../../types/erp';
import { getInvoiceDetail, returnInvoiceItems, voidInvoice } from './invoices.api';

interface InvoiceDetailModalProps {
  publicId: string | null;
  onClose: () => void;
}

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

export const InvoiceDetailModal: React.FC<InvoiceDetailModalProps> = ({
  publicId,
  onClose,
}) => {
  const { shop } = useAuthStore();
  const queryClient = useQueryClient();

  const [isVoidModalOpen, setIsVoidModalOpen] = useState(false);
  const [voidReason, setVoidReason] = useState('');
  const [voidError, setVoidError] = useState<string | null>(null);

  const [isReturnModalOpen, setIsReturnModalOpen] = useState(false);
  const [returnReason, setReturnReason] = useState('');
  const [returnQuantities, setReturnQuantities] = useState<Record<number, string>>({});
  const [returnError, setReturnError] = useState<string | null>(null);

  const { data: invoice, isLoading, isError } = useQuery<InvoiceResponse>({
    queryKey: ['invoices', 'detail', publicId],
    queryFn: () => getInvoiceDetail(publicId!),
    enabled: Boolean(publicId),
  });

  // Compute already returned quantities per invoice_item_id using Decimal
  const returnedByItemId = useMemo(() => {
    const map: Record<number, Decimal> = {};
    if (!invoice?.returns) return map;
    for (const ret of invoice.returns) {
      for (const retItem of ret.items) {
        const prev = map[retItem.invoice_item] ?? new Decimal(0);
        map[retItem.invoice_item] = prev.plus(parseQuantity(retItem.quantity));
      }
    }
    return map;
  }, [invoice]);

  const voidMutation = useMutation({
    mutationFn: (reason: string) => voidInvoice(publicId!, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setIsVoidModalOpen(false);
      setVoidReason('');
      setVoidError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as { detail?: string; reason?: string[] } | undefined;
        setVoidError(data?.detail || data?.reason?.[0] || 'Failed to void invoice.');
      } else {
        setVoidError('An unexpected error occurred while voiding.');
      }
    },
  });

  const returnMutation = useMutation({
    mutationFn: (payload: { reason: string; items: { invoice_item_id: number; quantity: string }[] }) =>
      returnInvoiceItems(publicId!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setIsReturnModalOpen(false);
      setReturnReason('');
      setReturnQuantities({});
      setReturnError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as { detail?: string; reason?: string[]; items?: string[] } | undefined;
        setReturnError(
          data?.detail || data?.reason?.[0] || data?.items?.[0] || 'Failed to process sales return.'
        );
      } else {
        setReturnError('An unexpected error occurred while processing return.');
      }
    },
  });

  if (!publicId) return null;

  const handleOpenReturnModal = () => {
    if (!invoice) return;
    const initial: Record<number, string> = {};
    for (const item of invoice.items) {
      initial[item.id] = '0.000';
    }
    setReturnQuantities(initial);
    setReturnReason('');
    setReturnError(null);
    setIsReturnModalOpen(true);
  };

  const handleVoidSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setVoidError(null);
    const trimmed = voidReason.trim();
    if (trimmed.length < 3) {
      setVoidError('Please enter a void reason (at least 3 characters).');
      return;
    }
    voidMutation.mutate(trimmed);
  };

  const handleReturnSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setReturnError(null);
    if (!invoice) return;

    const trimmedReason = returnReason.trim();
    if (trimmedReason.length < 3) {
      setReturnError('Please enter a return reason (at least 3 characters).');
      return;
    }

    const itemsPayload: { invoice_item_id: number; quantity: string }[] = [];

    for (const item of invoice.items) {
      const rawQty = returnQuantities[item.id] ?? '0';
      const reqQty = parseQuantity(rawQty);
      const returnedSoFar = returnedByItemId[item.id] ?? new Decimal(0);
      const remainingQty = parseQuantity(item.quantity).minus(returnedSoFar);

      if (reqQty.isNegative()) {
        setReturnError(`Return quantity for "${item.product_name}" cannot be negative.`);
        return;
      }

      if (reqQty.gt(remainingQty)) {
        setReturnError(
          `Return quantity for "${item.product_name}" exceeds remaining returnable quantity (${formatQuantityFixed(remainingQty)}).`
        );
        return;
      }

      if (reqQty.gt(0)) {
        itemsPayload.push({
          invoice_item_id: item.id,
          quantity: formatQuantityFixed(reqQty),
        });
      }
    }

    if (itemsPayload.length === 0) {
      setReturnError('Select a return quantity greater than 0 for at least one item.');
      return;
    }

    returnMutation.mutate({
      reason: trimmedReason,
      items: itemsPayload,
    });
  };

  const canVoidOrReturn = invoice && invoice.status !== 'VOIDED';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-lg rounded-2xl bg-white p-5 sm:p-6 shadow-2xl border border-slate-100 max-h-[92vh] flex flex-col">
        <button
          type="button"
          onClick={onClose}
          aria-label="Close invoice detail"
          className="print:hidden absolute top-3 right-3 inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 cursor-pointer"
        >
          <X className="h-5 w-5" />
        </button>

        {isLoading && (
          <div className="py-16 flex flex-col items-center gap-3 text-slate-500">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
            <span className="text-sm font-medium">Loading invoice details...</span>
          </div>
        )}

        {isError && (
          <div className="py-10 text-center space-y-3">
            <AlertCircle className="h-8 w-8 mx-auto text-red-500" />
            <p className="text-sm font-semibold text-red-700">Failed to load invoice details.</p>
          </div>
        )}

        {invoice && (
          <>
            {/* Printable Thermal Receipt Area */}
            <div id="printable-receipt" className="flex-1 overflow-y-auto pr-1 space-y-4">
              <div className="text-center border-b border-dashed border-slate-300 pb-3">
                <h3 className="text-lg font-black text-slate-900 tracking-tight">
                  {shop?.name || 'Modulr Store'}
                </h3>
                {shop?.address && <p className="text-xs text-slate-500">{shop.address}</p>}
                {shop?.phone && <p className="text-xs text-slate-500">{shop.phone}</p>}

                <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
                  <span className="rounded bg-indigo-50 px-2.5 py-0.5 text-xs font-bold text-indigo-700">
                    {invoice.invoice_number}
                  </span>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${getStatusBadgeClass(
                      invoice.status
                    )}`}
                  >
                    {invoice.status_display || invoice.status}
                  </span>
                </div>

                <p className="text-[11px] text-slate-500 mt-1.5">
                  {new Date(invoice.created_at).toLocaleString()}
                  {invoice.cashier_name ? ` • Cashier: ${invoice.cashier_name}` : ''}
                </p>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Customer: <span className="font-semibold">{invoice.customer_name || 'Walk-in Customer'}</span>
                  {invoice.customer_phone ? ` (${invoice.customer_phone})` : ''}
                </p>
              </div>

              {invoice.status === 'VOIDED' && invoice.void_reason && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-700">
                  <span className="font-bold">Void Reason:</span> {invoice.void_reason}
                </div>
              )}

              {/* Items Summary */}
              <div className="space-y-1.5 text-xs">
                {invoice.items.map((item) => {
                  const returned = returnedByItemId[item.id] ?? new Decimal(0);
                  return (
                    <div key={item.id} className="flex justify-between py-1.5 border-b border-slate-100">
                      <div>
                        <span className="font-semibold text-slate-800">{item.product_name}</span>
                        <span className="text-slate-500 block text-[11px]">
                          {formatQuantityFixed(item.quantity)} x {formatMoneyFixed(item.unit_price)}
                          {returned.gt(0) && (
                            <span className="ml-2 font-semibold text-amber-700">
                              (Returned: {formatQuantityFixed(returned)})
                            </span>
                          )}
                        </span>
                      </div>
                      <span className="font-bold text-slate-900">
                        {formatLKR(item.line_total)}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Financial Totals */}
              <div className="border-t border-slate-200 pt-2.5 space-y-1 text-xs">
                <div className="flex justify-between text-slate-600">
                  <span>Subtotal</span>
                  <span>{formatLKR(invoice.subtotal)}</span>
                </div>

                {parseMoney(invoice.discount).gt(0) && (
                  <div className="flex justify-between text-slate-600">
                    <span>Discount</span>
                    <span>- {formatLKR(invoice.discount)}</span>
                  </div>
                )}

                {invoice.tax_mode !== 'NONE' && parseMoney(invoice.tax_amount).gt(0) && (
                  <div className="flex justify-between text-slate-600">
                    <span>
                      {invoice.tax_label || 'Tax'} ({invoice.tax_rate_pct}%
                      {invoice.tax_mode === 'INCLUSIVE' ? ' incl.' : ''})
                    </span>
                    <span>{formatLKR(invoice.tax_amount)}</span>
                  </div>
                )}

                <div className="flex justify-between text-sm font-extrabold text-slate-900 pt-1.5 border-t border-dashed border-slate-300">
                  <span>Total Amount</span>
                  <span>{formatLKR(invoice.total_amount)}</span>
                </div>

                <div className="flex justify-between text-[11px] text-slate-500">
                  <span>Payment Method</span>
                  <span className="font-bold">{invoice.payment_method}</span>
                </div>

                <div className="flex justify-between text-[11px] text-slate-500">
                  <span>Amount Paid</span>
                  <span className="font-bold">{formatLKR(invoice.amount_paid)}</span>
                </div>

                {parseMoney(invoice.credit_amount).gt(0) && (
                  <div className="flex justify-between text-xs font-bold text-amber-700">
                    <span>Credit Balance</span>
                    <span>{formatLKR(invoice.credit_amount)}</span>
                  </div>
                )}
              </div>

              {/* Returns / Credit Notes History */}
              {invoice.returns && invoice.returns.length > 0 && (
                <div className="border-t border-slate-200 pt-3 space-y-2">
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Credit Notes / Returns
                  </h4>
                  {invoice.returns.map((ret) => (
                    <div
                      key={ret.public_id}
                      className="rounded-lg border border-amber-200 bg-amber-50/50 p-2.5 text-[11px] space-y-1"
                    >
                      <div className="flex justify-between font-bold text-amber-900">
                        <span>{ret.return_number}</span>
                        <span>Refund: {formatLKR(ret.total_refund_amount)}</span>
                      </div>
                      <p className="text-slate-600">Reason: {ret.reason}</p>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-center text-[11px] text-slate-400 border-t border-dashed border-slate-300 pt-3">
                Thank you for shopping with us!
              </div>
            </div>

            {/* Action Buttons (Hidden when printing) */}
            <div className="print:hidden mt-4 pt-4 border-t border-slate-100 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="min-h-[44px] flex items-center justify-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  <Printer className="h-4 w-4" />
                  <span>Reprint Receipt</span>
                </button>

                {invoice.whatsapp_share_url && (
                  <a
                    href={invoice.whatsapp_share_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="min-h-[44px] flex items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-700"
                  >
                    <Send className="h-4 w-4" />
                    <span>WhatsApp</span>
                  </a>
                )}
              </div>

              {canVoidOrReturn && (
                <div className="grid grid-cols-2 gap-2">
                  <Can permission="sales.return_invoice">
                    <button
                      type="button"
                      onClick={handleOpenReturnModal}
                      disabled={invoice.status === 'RETURNED'}
                      className="min-h-[44px] flex items-center justify-center gap-1.5 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800 hover:bg-amber-100 disabled:opacity-40 cursor-pointer"
                    >
                      <RotateCcw className="h-4 w-4" />
                      <span>Return Items</span>
                    </button>
                  </Can>

                  <Can permission="sales.void_invoice">
                    <button
                      type="button"
                      onClick={() => {
                        setVoidReason('');
                        setVoidError(null);
                        setIsVoidModalOpen(true);
                      }}
                      className="min-h-[44px] flex items-center justify-center gap-1.5 rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-100 cursor-pointer"
                    >
                      <Ban className="h-4 w-4" />
                      <span>Void Invoice</span>
                    </button>
                  </Can>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Void Invoice Confirmation Modal */}
      {isVoidModalOpen && invoice && (
        <div className="print:hidden fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-base font-bold text-slate-900">
                Void Invoice {invoice.invoice_number}
              </h4>
              <button
                type="button"
                onClick={() => setIsVoidModalOpen(false)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600">
              Voiding restores all product stock and reverses any customer credit issued on this
              invoice. This action cannot be undone.
            </p>

            {voidError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{voidError}</span>
              </div>
            )}

            <form onSubmit={handleVoidSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Void Reason *
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={voidReason}
                  onChange={(e) => setVoidReason(e.target.value)}
                  placeholder="e.g. Duplicate checkout or customer cancelled"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-red-600 focus:outline-none focus:ring-1 focus:ring-red-600"
                />
              </div>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsVoidModalOpen(false)}
                  className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={voidMutation.isPending}
                  className="min-h-[44px] rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-50 cursor-pointer"
                >
                  {voidMutation.isPending ? 'Voiding...' : 'Confirm Void'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Sales Return / Credit Note Modal */}
      {isReturnModalOpen && invoice && (
        <div className="print:hidden fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-200 max-h-[90vh] flex flex-col space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-base font-bold text-slate-900">
                Sales Return — {invoice.invoice_number}
              </h4>
              <button
                type="button"
                onClick={() => setIsReturnModalOpen(false)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {returnError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{returnError}</span>
              </div>
            )}

            <form onSubmit={handleReturnSubmit} className="flex-1 overflow-y-auto space-y-4">
              <div className="space-y-2.5">
                {invoice.items.map((item) => {
                  const returnedSoFar = returnedByItemId[item.id] ?? new Decimal(0);
                  const remainingQty = parseQuantity(item.quantity).minus(returnedSoFar);
                  const disabled = remainingQty.lte(0);

                  return (
                    <div
                      key={item.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3 text-xs"
                    >
                      <div className="min-w-0">
                        <p className="font-bold text-slate-900 truncate">{item.product_name}</p>
                        <p className="text-[11px] text-slate-500">
                          Sold: {formatQuantityFixed(item.quantity)} • Returnable:{' '}
                          <span className="font-semibold text-slate-700">
                            {formatQuantityFixed(remainingQty)}
                          </span>
                        </p>
                      </div>

                      <input
                        type="number"
                        step="0.001"
                        min="0"
                        max={formatQuantityFixed(remainingQty)}
                        disabled={disabled}
                        value={returnQuantities[item.id] ?? '0.000'}
                        onChange={(e) =>
                          setReturnQuantities((prev) => ({
                            ...prev,
                            [item.id]: e.target.value,
                          }))
                        }
                        className="w-24 min-h-[44px] rounded-lg border border-slate-300 px-2.5 py-2 text-right text-xs font-bold text-slate-900 focus:border-indigo-600 focus:outline-none disabled:bg-slate-100"
                      />
                    </div>
                  );
                })}
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Return Reason *
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={returnReason}
                  onChange={(e) => setReturnReason(e.target.value)}
                  placeholder="e.g. Damaged item or wrong size"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsReturnModalOpen(false)}
                  className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={returnMutation.isPending}
                  className="min-h-[44px] rounded-xl bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50 cursor-pointer"
                >
                  {returnMutation.isPending ? 'Processing...' : 'Submit Return'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
