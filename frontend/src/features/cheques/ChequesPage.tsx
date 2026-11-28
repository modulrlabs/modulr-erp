import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Plus,
  RefreshCw,
  Search,
  X,
  XCircle,
} from 'lucide-react';
import { Can } from '../../components/Can';
import { formatLKR, formatMoneyFixed, parseMoney, sumMoney } from '../../lib/money';
import type { PDCheque, PDChequeStatus } from '../../types/erp';
import { getCustomers } from '../customers/customers.api';
import {
  createPDCheque,
  getPDCheques,
  getUpcomingPDCheques,
  updatePDChequeStatus,
} from './cheques.api';

function getChequeStatusBadgeClass(status: PDChequeStatus): string {
  switch (status) {
    case 'PENDING':
      return 'bg-amber-50 text-amber-800 border-amber-200';
    case 'CLEARED':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'BOUNCED':
      return 'bg-red-50 text-red-700 border-red-200';
  }
}

const STATUS_TABS: { label: string; value: PDChequeStatus | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Pending', value: 'PENDING' },
  { label: 'Cleared', value: 'CLEARED' },
  { label: 'Bounced', value: 'BOUNCED' },
];

export const ChequesPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<PDChequeStatus | ''>('');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Add PD Cheque Modal
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [customerSearch, setCustomerSearch] = useState('');
  const [newCheque, setNewCheque] = useState({
    customer: '',
    cheque_number: '',
    bank_name: '',
    amount: '',
    due_date: '',
    notes: '',
  });
  const [addError, setAddError] = useState<string | null>(null);

  // Confirm Status Update Modal
  const [statusConfirm, setStatusConfirm] = useState<{
    cheque: PDCheque;
    nextStatus: 'CLEARED' | 'BOUNCED';
  } | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['cheques', { page, status: statusFilter, search: debouncedSearch }],
    queryFn: () =>
      getPDCheques({
        page,
        status: statusFilter || undefined,
        search: debouncedSearch || undefined,
      }),
  });

  const { data: upcomingData } = useQuery({
    queryKey: ['cheques', 'upcoming'],
    queryFn: getUpcomingPDCheques,
  });

  const { data: customersData } = useQuery({
    queryKey: ['customers', { page_size: 100 }],
    queryFn: () => getCustomers({ page_size: 100 }),
    enabled: isAddModalOpen,
  });

  const upcomingCheques = useMemo(() => upcomingData?.results ?? [], [upcomingData]);
  const upcomingCount = upcomingData?.count ?? upcomingCheques.length;
  const upcomingTotalDec = useMemo(
    () => sumMoney(upcomingCheques.map((c) => c.amount)),
    [upcomingCheques]
  );

  const filteredModalCustomers = useMemo(() => {
    const list = customersData?.results ?? [];
    const q = customerSearch.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (c) => c.name.toLowerCase().includes(q) || (c.phone && c.phone.toLowerCase().includes(q))
    );
  }, [customersData, customerSearch]);

  const createMutation = useMutation({
    mutationFn: createPDCheque,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cheques'] });
      queryClient.invalidateQueries({ queryKey: ['cheques', 'upcoming'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setIsAddModalOpen(false);
      setNewCheque({
        customer: '',
        cheque_number: '',
        bank_name: '',
        amount: '',
        due_date: '',
        notes: '',
      });
      setCustomerSearch('');
      setAddError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as Record<string, string | string[]> | undefined;
        if (resp) {
          const firstKey = Object.keys(resp)[0];
          const val = resp[firstKey];
          setAddError(`${firstKey}: ${Array.isArray(val) ? val[0] : val}`);
        } else {
          setAddError('Failed to record PD cheque.');
        }
      } else {
        setAddError('An unexpected error occurred.');
      }
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ publicId, status }: { publicId: string; status: 'CLEARED' | 'BOUNCED' }) =>
      updatePDChequeStatus(publicId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cheques'] });
      queryClient.invalidateQueries({ queryKey: ['cheques', 'upcoming'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setStatusConfirm(null);
      setStatusError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as { detail?: string } | undefined;
        setStatusError(resp?.detail || 'Failed to update cheque status.');
      } else {
        setStatusError('An unexpected error occurred.');
      }
    },
  });

  const cheques = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasNext = Boolean(data?.next);
  const hasPrevious = Boolean(data?.previous);

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);

    if (!newCheque.cheque_number.trim() || !newCheque.bank_name.trim() || !newCheque.due_date) {
      setAddError('Cheque number, bank name, and due date are required.');
      return;
    }

    const amountDec = parseMoney(newCheque.amount);
    if (amountDec.lte(0)) {
      setAddError('Cheque amount must be greater than Rs. 0.00.');
      return;
    }

    createMutation.mutate({
      customer: newCheque.customer ? parseInt(newCheque.customer, 10) : null,
      cheque_number: newCheque.cheque_number.trim(),
      bank_name: newCheque.bank_name.trim(),
      amount: formatMoneyFixed(amountDec),
      due_date: newCheque.due_date,
      notes: newCheque.notes.trim(),
    });
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            Post-Dated Cheques Tracker
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Monitor upcoming cheque due dates and track clearance status
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs sm:text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <Can permission="cheques.manage">
            <button
              type="button"
              onClick={() => {
                setAddError(null);
                setIsAddModalOpen(true);
              }}
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs sm:text-sm font-bold text-white shadow-sm hover:bg-indigo-700 cursor-pointer"
            >
              <Plus className="h-4 w-4" />
              <span>Add Cheque</span>
            </button>
          </Can>
        </div>
      </div>

      {/* Upcoming 7-Day Alert Banner */}
      {upcomingCount > 0 && (
        <div
          role="status"
          className="rounded-xl border border-amber-300 bg-amber-50 p-4 shadow-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
        >
          <div className="flex items-start sm:items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5 sm:mt-0" />
            <div className="text-xs sm:text-sm text-amber-900">
              <span className="font-bold">
                {upcomingCount} pending cheque{upcomingCount === 1 ? '' : 's'} due within 7 days
              </span>{' '}
              — Total:{' '}
              <span className="font-black">{formatLKR(upcomingTotalDec)}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setStatusFilter('PENDING');
              setPage(1);
            }}
            className="min-h-[44px] rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-bold text-amber-900 hover:bg-amber-100 cursor-pointer shrink-0"
          >
            View Pending
          </button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
        <div className="flex flex-wrap gap-2">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.label}
              type="button"
              onClick={() => {
                setStatusFilter(tab.value);
                setPage(1);
              }}
              className={`min-h-[44px] rounded-lg px-4 py-2 text-xs sm:text-sm font-bold transition-colors cursor-pointer ${
                statusFilter === tab.value
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative">
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
            placeholder="Search by cheque number, bank name, or customer..."
            className="block w-full min-h-[44px] rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
          />
        </div>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs sm:text-sm font-medium text-red-700 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>Failed to load PD cheques. Please try again.</span>
        </div>
      )}

      {/* Results Container */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading && cheques.length === 0 ? (
          <div className="py-12 flex flex-col items-center gap-2 text-slate-400">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
            <span className="text-xs">Loading PD cheques...</span>
          </div>
        ) : cheques.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <CreditCard className="h-8 w-8 mx-auto text-slate-300 stroke-[1.5]" />
            <p className="mt-2 text-sm font-semibold text-slate-700">No PD cheques found</p>
            <p className="text-xs text-slate-400">Try adjusting your status tab or search filter</p>
          </div>
        ) : (
          <>
            {/* Tablet / Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left text-xs divide-y divide-slate-100">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="py-3 pl-4 pr-3">Cheque #</th>
                    <th className="py-3 px-3">Bank</th>
                    <th className="py-3 px-3">Customer</th>
                    <th className="py-3 px-3">Due Date</th>
                    <th className="py-3 px-3 text-right">Amount</th>
                    <th className="py-3 px-3 text-center">Status</th>
                    <th className="py-3 pr-4 pl-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {cheques.map((cheque) => (
                    <tr key={cheque.public_id} className="hover:bg-slate-50/70">
                      <td className="py-3 pl-4 pr-3 font-mono font-bold text-slate-900">
                        {cheque.cheque_number}
                      </td>
                      <td className="py-3 px-3 text-slate-700">{cheque.bank_name}</td>
                      <td className="py-3 px-3 text-slate-700">
                        {cheque.customer_name || <span className="text-slate-400">—</span>}
                      </td>
                      <td className="py-3 px-3 text-slate-600">{cheque.due_date}</td>
                      <td className="py-3 px-3 text-right font-bold text-slate-900">
                        {formatLKR(cheque.amount)}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span
                          className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getChequeStatusBadgeClass(
                            cheque.status
                          )}`}
                        >
                          {cheque.status_display || cheque.status}
                        </span>
                      </td>
                      <td className="py-3 pr-4 pl-3 text-right">
                        {cheque.status === 'PENDING' ? (
                          <Can permission="cheques.manage">
                            <div className="inline-flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setStatusError(null);
                                  setStatusConfirm({ cheque, nextStatus: 'CLEARED' });
                                }}
                                className="inline-flex min-h-[44px] items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 cursor-pointer"
                              >
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                <span>Mark Cleared</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setStatusError(null);
                                  setStatusConfirm({ cheque, nextStatus: 'BOUNCED' });
                                }}
                                className="inline-flex min-h-[44px] items-center gap-1 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700 hover:bg-red-100 cursor-pointer"
                              >
                                <XCircle className="h-3.5 w-3.5" />
                                <span>Mark Bounced</span>
                              </button>
                            </div>
                          </Can>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Stacked Cards */}
            <div className="md:hidden divide-y divide-slate-100">
              {cheques.map((cheque) => (
                <div key={cheque.public_id} className="p-4 space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-mono font-bold text-slate-900">
                        #{cheque.cheque_number}
                      </p>
                      <p className="text-xs text-slate-600">
                        {cheque.bank_name} • Due: {cheque.due_date}
                      </p>
                    </div>
                    <span
                      className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getChequeStatusBadgeClass(
                        cheque.status
                      )}`}
                    >
                      {cheque.status_display || cheque.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs text-slate-600">
                    <span>{cheque.customer_name || 'No customer linked'}</span>
                    <span className="text-base font-black text-slate-900">
                      {formatLKR(cheque.amount)}
                    </span>
                  </div>

                  {cheque.status === 'PENDING' && (
                    <Can permission="cheques.manage">
                      <div className="grid grid-cols-2 gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => {
                            setStatusError(null);
                            setStatusConfirm({ cheque, nextStatus: 'CLEARED' });
                          }}
                          className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-700 cursor-pointer"
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          <span>Mark Cleared</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setStatusError(null);
                            setStatusConfirm({ cheque, nextStatus: 'BOUNCED' });
                          }}
                          className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-100 cursor-pointer"
                        >
                          <XCircle className="h-4 w-4" />
                          <span>Mark Bounced</span>
                        </button>
                      </div>
                    </Can>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Pagination Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600">
          <span>
            Showing <span className="font-semibold text-slate-800">{cheques.length}</span> of{' '}
            <span className="font-semibold text-slate-800">{totalCount}</span> cheques (Page {page})
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

      {/* Add PD Cheque Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Record PD Cheque</h2>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {addError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{addError}</span>
              </div>
            )}

            <form onSubmit={handleAddSubmit} className="space-y-4 text-xs font-medium">
              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Customer (Optional)
                </label>
                <input
                  type="text"
                  value={customerSearch}
                  onChange={(e) => setCustomerSearch(e.target.value)}
                  placeholder="Filter customer list..."
                  className="mb-1.5 block w-full min-h-[44px] rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-900 focus:border-indigo-600 focus:bg-white focus:outline-none"
                />
                <select
                  value={newCheque.customer}
                  onChange={(e) => setNewCheque({ ...newCheque, customer: e.target.value })}
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                >
                  <option value="">-- No Customer Linked --</option>
                  {filteredModalCustomers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.phone ? `(${c.phone})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Cheque Number *
                  </label>
                  <input
                    type="text"
                    required
                    value={newCheque.cheque_number}
                    onChange={(e) => setNewCheque({ ...newCheque, cheque_number: e.target.value })}
                    placeholder="e.g. 458921"
                    className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Bank Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={newCheque.bank_name}
                    onChange={(e) => setNewCheque({ ...newCheque, bank_name: e.target.value })}
                    placeholder="e.g. Sampath Bank"
                    className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Amount (LKR) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={newCheque.amount}
                    onChange={(e) => setNewCheque({ ...newCheque, amount: e.target.value })}
                    placeholder="0.00"
                    className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Due Date *
                  </label>
                  <input
                    type="date"
                    required
                    value={newCheque.due_date}
                    onChange={(e) => setNewCheque({ ...newCheque, due_date: e.target.value })}
                    className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Notes (Optional)
                </label>
                <input
                  type="text"
                  value={newCheque.notes}
                  onChange={(e) => setNewCheque({ ...newCheque, notes: e.target.value })}
                  placeholder="e.g. Branch or invoice reference"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="min-h-[44px] rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  {createMutation.isPending ? 'Saving...' : 'Save Cheque'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Status Confirmation Modal */}
      {statusConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">
                Mark Cheque #{statusConfirm.cheque.cheque_number} as{' '}
                {statusConfirm.nextStatus === 'CLEARED' ? 'Cleared' : 'Bounced'}?
              </h2>
              <button
                type="button"
                onClick={() => setStatusConfirm(null)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600">
              Bank: <span className="font-semibold">{statusConfirm.cheque.bank_name}</span> • Amount:{' '}
              <span className="font-bold">{formatLKR(statusConfirm.cheque.amount)}</span>
            </p>

            {statusError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{statusError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setStatusConfirm(null)}
                className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={statusMutation.isPending}
                onClick={() =>
                  statusMutation.mutate({
                    publicId: statusConfirm.cheque.public_id,
                    status: statusConfirm.nextStatus,
                  })
                }
                className={`min-h-[44px] rounded-xl px-4 py-2 text-xs font-bold text-white disabled:opacity-50 cursor-pointer ${
                  statusConfirm.nextStatus === 'CLEARED'
                    ? 'bg-emerald-600 hover:bg-emerald-700'
                    : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {statusMutation.isPending
                  ? 'Updating...'
                  : statusConfirm.nextStatus === 'CLEARED'
                  ? 'Confirm Cleared'
                  : 'Confirm Bounced'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
