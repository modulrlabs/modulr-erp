import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  Banknote,
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import { Can } from '../../components/Can';
import { formatLKR, formatMoneyFixed, parseMoney } from '../../lib/money';
import type { CreditPaymentMethod, Customer } from '../../types/erp';
import {
  createCustomer,
  deleteCustomer,
  getCustomers,
  recordCreditPayment,
} from './customers.api';

export const CustomersPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [hasCreditOnly, setHasCreditOnly] = useState(false);

  // Add Customer Modal
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newCustomer, setNewCustomer] = useState({
    name: '',
    phone: '',
    address: '',
  });
  const [addError, setAddError] = useState<string | null>(null);

  // Settle Credit Payment Modal
  const [settleTarget, setSettleTarget] = useState<Customer | null>(null);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<CreditPaymentMethod>('CASH');
  const [paymentNotes, setPaymentNotes] = useState('');
  const [paymentError, setPaymentError] = useState<string | null>(null);

  // Delete Confirmation Modal
  const [deleteTarget, setDeleteTarget] = useState<Customer | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['customers', { page, search: debouncedSearch, hasCreditOnly }],
    queryFn: () =>
      getCustomers({
        page,
        search: debouncedSearch || undefined,
        has_credit: hasCreditOnly ? true : undefined,
      }),
  });

  const createMutation = useMutation({
    mutationFn: createCustomer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      setIsAddModalOpen(false);
      setNewCustomer({ name: '', phone: '', address: '' });
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
          setAddError('Failed to create customer.');
        }
      } else {
        setAddError('An unexpected error occurred.');
      }
    },
  });

  const settleMutation = useMutation({
    mutationFn: recordCreditPayment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setSettleTarget(null);
      setPaymentAmount('');
      setPaymentNotes('');
      setPaymentError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as
          | { detail?: string; amount_paid?: string[]; customer?: string[] }
          | undefined;
        setPaymentError(
          resp?.detail ||
            resp?.amount_paid?.[0] ||
            resp?.customer?.[0] ||
            'Failed to record credit payment.'
        );
      } else {
        setPaymentError('An unexpected error occurred.');
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (publicId: string) => deleteCustomer(publicId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setDeleteTarget(null);
      setDeleteError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as { detail?: string } | string[] | undefined;
        if (Array.isArray(resp)) {
          setDeleteError(resp[0] || 'Cannot delete customer.');
        } else {
          setDeleteError(resp?.detail || 'Cannot delete customer.');
        }
      } else {
        setDeleteError('An unexpected error occurred.');
      }
    },
  });

  const customers = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasNext = Boolean(data?.next);
  const hasPrevious = Boolean(data?.previous);

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);
    if (!newCustomer.name.trim()) {
      setAddError('Customer name is required.');
      return;
    }
    createMutation.mutate({
      name: newCustomer.name.trim(),
      phone: newCustomer.phone.trim(),
      address: newCustomer.address.trim(),
    });
  };

  const handleSettleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPaymentError(null);
    if (!settleTarget) return;

    const amountDec = parseMoney(paymentAmount);
    const balanceDec = parseMoney(settleTarget.total_credit_balance);

    if (amountDec.lte(0)) {
      setPaymentError('Payment amount must be greater than Rs. 0.00.');
      return;
    }

    if (amountDec.gt(balanceDec)) {
      setPaymentError(
        `Payment amount cannot exceed outstanding balance (${formatLKR(balanceDec)}).`
      );
      return;
    }

    settleMutation.mutate({
      customer: settleTarget.id,
      amount_paid: formatMoneyFixed(amountDec),
      payment_method: paymentMethod,
      notes: paymentNotes.trim(),
    });
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            Customers &amp; Credit Ledger
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Track customer credit balances and record debt settlements
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

          <Can permission="credit.manage_customers">
            <button
              type="button"
              onClick={() => {
                setNewCustomer({ name: '', phone: '', address: '' });
                setAddError(null);
                setIsAddModalOpen(true);
              }}
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs sm:text-sm font-bold text-white shadow-sm hover:bg-indigo-700 cursor-pointer"
            >
              <UserPlus className="h-4 w-4" />
              <span>Add Customer</span>
            </button>
          </Can>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
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
            placeholder="Search by customer name or phone..."
            className="block w-full min-h-[44px] rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
          />
        </div>

        <button
          type="button"
          onClick={() => {
            setHasCreditOnly((prev) => !prev);
            setPage(1);
          }}
          className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border px-4 py-2 text-xs sm:text-sm font-semibold transition-colors cursor-pointer shrink-0 ${
            hasCreditOnly
              ? 'border-amber-400 bg-amber-50 text-amber-800'
              : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          <Banknote className="h-4 w-4 text-amber-600" />
          <span>Has Credit Only</span>
        </button>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs sm:text-sm font-medium text-red-700 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>Failed to load customers. Please try again.</span>
        </div>
      )}

      {/* Results Container */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading && customers.length === 0 ? (
          <div className="py-12 flex flex-col items-center gap-2 text-slate-400">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
            <span className="text-xs">Loading customers...</span>
          </div>
        ) : customers.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <Users className="h-8 w-8 mx-auto text-slate-300 stroke-[1.5]" />
            <p className="mt-2 text-sm font-semibold text-slate-700">No customers found</p>
            <p className="text-xs text-slate-400">
              Try adjusting your search or add a new customer
            </p>
          </div>
        ) : (
          <>
            {/* Tablet / Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left text-xs divide-y divide-slate-100">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="py-3 pl-4 pr-3">Customer Name</th>
                    <th className="py-3 px-3">Phone</th>
                    <th className="py-3 px-3">Address</th>
                    <th className="py-3 px-3 text-right">Outstanding Credit</th>
                    <th className="py-3 pr-4 pl-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {customers.map((customer) => {
                    const hasDebt = parseMoney(customer.total_credit_balance).gt(0);
                    return (
                      <tr key={customer.public_id} className="hover:bg-slate-50/70">
                        <td className="py-3 pl-4 pr-3 font-bold text-slate-900">
                          {customer.name}
                        </td>
                        <td className="py-3 px-3 text-slate-600">
                          {customer.phone || <span className="text-slate-300">—</span>}
                        </td>
                        <td className="py-3 px-3 text-slate-500 max-w-xs truncate">
                          {customer.address || <span className="text-slate-300">—</span>}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <span
                            className={`font-bold ${
                              hasDebt ? 'text-amber-700' : 'text-emerald-700'
                            }`}
                          >
                            {formatLKR(customer.total_credit_balance)}
                          </span>
                        </td>
                        <td className="py-3 pr-4 pl-3 text-right">
                          <div className="inline-flex items-center justify-end gap-2">
                            {hasDebt && (
                              <Can permission="credit.record_payment">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setSettleTarget(customer);
                                    setPaymentAmount(formatMoneyFixed(customer.total_credit_balance));
                                    setPaymentMethod('CASH');
                                    setPaymentNotes('');
                                    setPaymentError(null);
                                  }}
                                  className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 cursor-pointer"
                                >
                                  <Banknote className="h-3.5 w-3.5" />
                                  <span>Settle Payment</span>
                                </button>
                              </Can>
                            )}

                            <Can permission="credit.manage_customers">
                              <button
                                type="button"
                                onClick={() => {
                                  setDeleteTarget(customer);
                                  setDeleteError(null);
                                }}
                                aria-label={`Delete ${customer.name}`}
                                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-red-200 hover:bg-red-50 hover:text-red-600 cursor-pointer"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </Can>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Stacked Cards */}
            <div className="md:hidden divide-y divide-slate-100">
              {customers.map((customer) => {
                const hasDebt = parseMoney(customer.total_credit_balance).gt(0);
                return (
                  <div key={customer.public_id} className="p-4 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-bold text-slate-900">{customer.name}</p>
                        <p className="text-xs text-slate-500">
                          {customer.phone || 'No phone number'}
                        </p>
                      </div>
                      <span
                        className={`text-sm font-black ${
                          hasDebt ? 'text-amber-700' : 'text-emerald-700'
                        }`}
                      >
                        {formatLKR(customer.total_credit_balance)}
                      </span>
                    </div>

                    {customer.address && (
                      <p className="text-xs text-slate-500">{customer.address}</p>
                    )}

                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      {hasDebt && (
                        <Can permission="credit.record_payment">
                          <button
                            type="button"
                            onClick={() => {
                              setSettleTarget(customer);
                              setPaymentAmount(formatMoneyFixed(customer.total_credit_balance));
                              setPaymentMethod('CASH');
                              setPaymentNotes('');
                              setPaymentError(null);
                            }}
                            className="flex-1 inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-700 cursor-pointer"
                          >
                            <Banknote className="h-4 w-4" />
                            <span>Settle Payment</span>
                          </button>
                        </Can>
                      )}

                      <Can permission="credit.manage_customers">
                        <button
                          type="button"
                          onClick={() => {
                            setDeleteTarget(customer);
                            setDeleteError(null);
                          }}
                          className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-100 cursor-pointer"
                        >
                          <Trash2 className="h-4 w-4" />
                          <span>Delete</span>
                        </button>
                      </Can>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Pagination Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600">
          <span>
            Showing <span className="font-semibold text-slate-800">{customers.length}</span> of{' '}
            <span className="font-semibold text-slate-800">{totalCount}</span> customers (Page{' '}
            {page})
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

      {/* Add Customer Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Add New Customer</h2>
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
                  Customer Name *
                </label>
                <input
                  type="text"
                  required
                  value={newCustomer.name}
                  onChange={(e) => setNewCustomer({ ...newCustomer, name: e.target.value })}
                  placeholder="e.g. Kamal Perera"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Phone Number
                </label>
                <input
                  type="text"
                  value={newCustomer.phone}
                  onChange={(e) => setNewCustomer({ ...newCustomer, phone: e.target.value })}
                  placeholder="e.g. 0771234567"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Address / Notes (Optional)
                </label>
                <input
                  type="text"
                  value={newCustomer.address}
                  onChange={(e) => setNewCustomer({ ...newCustomer, address: e.target.value })}
                  placeholder="e.g. 42 Galle Road, Colombo"
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
                  className="min-h-[44px] inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  <Plus className="h-4 w-4" />
                  <span>{createMutation.isPending ? 'Saving...' : 'Save Customer'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Settle Credit Payment Modal */}
      {settleTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Settle Credit Payment</h2>
              <button
                type="button"
                onClick={() => setSettleTarget(null)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs space-y-1">
              <p className="font-bold text-slate-900">{settleTarget.name}</p>
              <p className="text-amber-800">
                Current Outstanding Balance:{' '}
                <span className="font-black">{formatLKR(settleTarget.total_credit_balance)}</span>
              </p>
            </div>

            {paymentError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{paymentError}</span>
              </div>
            )}

            <form onSubmit={handleSettleSubmit} className="space-y-4 text-xs font-medium">
              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Amount Paid (LKR) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={formatMoneyFixed(settleTarget.total_credit_balance)}
                  required
                  value={paymentAmount}
                  onChange={(e) => setPaymentAmount(e.target.value)}
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Payment Method
                </label>
                <select
                  value={paymentMethod}
                  onChange={(e) => setPaymentMethod(e.target.value as CreditPaymentMethod)}
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600"
                >
                  <option value="CASH">Cash</option>
                  <option value="BANK_TRANSFER">Bank Transfer</option>
                  <option value="CHEQUE">Cheque</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Notes / Reference (Optional)
                </label>
                <input
                  type="text"
                  value={paymentNotes}
                  onChange={(e) => setPaymentNotes(e.target.value)}
                  placeholder="e.g. Receipt #104 or bank ref"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSettleTarget(null)}
                  className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={settleMutation.isPending}
                  className="min-h-[44px] rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 disabled:opacity-50 cursor-pointer"
                >
                  {settleMutation.isPending ? 'Recording...' : 'Record Payment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Customer Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">
                Delete Customer {deleteTarget.name}?
              </h2>
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600">
              This will archive the customer record. Customers with an outstanding credit balance
              cannot be deleted.
            </p>

            {deleteError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{deleteError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(deleteTarget.public_id)}
                className="min-h-[44px] rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-50 cursor-pointer"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
