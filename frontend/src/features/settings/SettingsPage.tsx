import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ClipboardList,
  Percent,
  Save,
  ShieldCheck,
} from 'lucide-react';
import { Can } from '../../components/Can';
import { useAnyPermission, usePermission } from '../../hooks/usePermission';
import type { ShopSettings, TaxMode } from '../../types/erp';
import { getAuditLogs, getShopSettings, updateShopSettings } from './settings.api';

type SettingsTab = 'tax' | 'managers' | 'audit';

const MANAGER_TOGGLES: {
  key: keyof Pick<
    ShopSettings,
    | 'managers_can_edit_products'
    | 'managers_can_view_cost_price'
    | 'managers_can_view_profit'
    | 'managers_can_manage_purchasing'
    | 'managers_can_manage_cashiers'
  >;
  label: string;
  description: string;
}[] = [
  {
    key: 'managers_can_edit_products',
    label: 'Manage Products & Categories',
    description: 'Allow managers to create and edit products, prices, and categories.',
  },
  {
    key: 'managers_can_view_cost_price',
    label: 'View Cost Prices',
    description: 'Allow managers to see product cost prices in inventory and invoices.',
  },
  {
    key: 'managers_can_view_profit',
    label: 'View Profit Metrics',
    description: 'Allow managers to view gross profit cards on the dashboard.',
  },
  {
    key: 'managers_can_manage_purchasing',
    label: 'Manage Purchasing & Stock Adjustments',
    description: 'Allow managers to record purchases and manual stock adjustments.',
  },
  {
    key: 'managers_can_manage_cashiers',
    label: 'Manage Cashier Accounts',
    description: 'Allow managers to create, deactivate, and reset passwords for Cashiers.',
  },
];

export const SettingsPage: React.FC = () => {
  const canManageShop = usePermission('settings.manage_shop');
  const canViewAudit = useAnyPermission(['audit.view_all', 'audit.view_staff']);
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<SettingsTab>(() =>
    canManageShop ? 'tax' : 'audit'
  );
  const [draft, setDraft] = useState<ShopSettings | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Audit Log state
  const [auditPage, setAuditPage] = useState(1);
  const [actionInput, setActionInput] = useState('');
  const [debouncedAction, setDebouncedAction] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedAction(actionInput.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [actionInput]);

  const {
    data: settingsData,
    isLoading: isLoadingSettings,
    isError: isSettingsError,
  } = useQuery({
    queryKey: ['shop-settings'],
    queryFn: getShopSettings,
    enabled: canManageShop,
  });

  const {
    data: auditData,
    isLoading: isLoadingAudit,
    isError: isAuditError,
  } = useQuery({
    queryKey: [
      'audit-logs',
      { page: auditPage, action: debouncedAction, dateFrom, dateTo },
    ],
    queryFn: () =>
      getAuditLogs({
        page: auditPage,
        action: debouncedAction || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    enabled: canViewAudit && activeTab === 'audit',
  });

  const updateMutation = useMutation({
    mutationFn: updateShopSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(['shop-settings'], updated);
      queryClient.invalidateQueries({ queryKey: ['shop-settings'] });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      setDraft(null);
      setSaveError(null);
      setSaveMessage('Shop settings saved successfully.');
      setTimeout(() => setSaveMessage(null), 3500);
    },
    onError: (err: unknown) => {
      setSaveMessage(null);
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as Record<string, string | string[]> | undefined;
        if (resp) {
          const firstKey = Object.keys(resp)[0];
          const val = resp[firstKey];
          setSaveError(`${firstKey}: ${Array.isArray(val) ? val[0] : val}`);
        } else {
          setSaveError('Failed to save shop settings.');
        }
      } else {
        setSaveError('An unexpected error occurred.');
      }
    },
  });

  const form = draft ?? settingsData;

  const updateField = <K extends keyof ShopSettings>(key: K, value: ShopSettings[K]) => {
    if (!form) return;
    setDraft({ ...form, [key]: value });
  };

  const handleSaveTaxSettings = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaveError(null);
    updateMutation.mutate({
      tax_mode: form.tax_mode,
      tax_rate_pct: form.tax_mode === 'NONE' ? '0.00' : form.tax_rate_pct,
      tax_label: form.tax_label.trim() || 'VAT',
      cashier_max_discount_pct: form.cashier_max_discount_pct,
    });
  };

  const handleSaveManagers = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaveError(null);
    updateMutation.mutate({
      managers_can_edit_products: form.managers_can_edit_products,
      managers_can_view_cost_price: form.managers_can_view_cost_price,
      managers_can_view_profit: form.managers_can_view_profit,
      managers_can_manage_purchasing: form.managers_can_manage_purchasing,
      managers_can_manage_cashiers: form.managers_can_manage_cashiers,
    });
  };

  const auditLogs = auditData?.results ?? [];
  const auditTotal = auditData?.count ?? 0;
  const auditHasNext = Boolean(auditData?.next);
  const auditHasPrev = Boolean(auditData?.previous);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
          Shop Settings &amp; Audit Logs
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
          Configure tax rules, cashier discount limits, manager permissions, and review security logs
        </p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        <Can permission="settings.manage_shop">
          <button
            type="button"
            onClick={() => setActiveTab('tax')}
            className={`min-h-[44px] inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs sm:text-sm font-bold transition-colors cursor-pointer ${
              activeTab === 'tax'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <Percent className="h-4 w-4" />
            <span>Tax &amp; POS Rules</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('managers')}
            className={`min-h-[44px] inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs sm:text-sm font-bold transition-colors cursor-pointer ${
              activeTab === 'managers'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <ShieldCheck className="h-4 w-4" />
            <span>Manager Permissions</span>
          </button>
        </Can>

        <Can anyOf={['audit.view_all', 'audit.view_staff']}>
          <button
            type="button"
            onClick={() => setActiveTab('audit')}
            className={`min-h-[44px] inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs sm:text-sm font-bold transition-colors cursor-pointer ${
              activeTab === 'audit'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <ClipboardList className="h-4 w-4" />
            <span>Audit Logs</span>
          </button>
        </Can>
      </div>

      {/* Save Feedback */}
      {saveMessage && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs sm:text-sm font-semibold text-emerald-800 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{saveMessage}</span>
        </div>
      )}

      {saveError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs sm:text-sm font-semibold text-red-700 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{saveError}</span>
        </div>
      )}

      {/* TAB 1: Tax & POS Rules */}
      {activeTab === 'tax' && canManageShop && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm max-w-2xl">
          {isLoadingSettings ? (
            <div className="py-8 text-center text-xs text-slate-500">Loading shop settings...</div>
          ) : isSettingsError || !form ? (
            <div className="text-xs text-red-600">Failed to load shop settings.</div>
          ) : (
            <form onSubmit={handleSaveTaxSettings} className="space-y-4 text-xs font-medium">
              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Tax Mode
                </label>
                <select
                  value={form.tax_mode}
                  onChange={(e) => {
                    const nextMode = e.target.value as TaxMode;
                    setDraft({
                      ...form,
                      tax_mode: nextMode,
                      tax_rate_pct: nextMode === 'NONE' ? '0.00' : form.tax_rate_pct,
                    });
                  }}
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white focus:border-indigo-600 focus:outline-none"
                >
                  <option value="NONE">No Tax (NONE)</option>
                  <option value="INCLUSIVE">Tax Inclusive (INCLUSIVE)</option>
                  <option value="EXCLUSIVE">Tax Exclusive (EXCLUSIVE)</option>
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Tax Rate (%)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="100"
                    disabled={form.tax_mode === 'NONE'}
                    value={form.tax_mode === 'NONE' ? '0.00' : form.tax_rate_pct}
                    onChange={(e) => updateField('tax_rate_pct', e.target.value)}
                    className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-900 focus:border-indigo-600 focus:outline-none disabled:bg-slate-100 disabled:text-slate-400"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                    Tax Label
                  </label>
                  <input
                    type="text"
                    maxLength={32}
                    value={form.tax_label}
                    onChange={(e) => updateField('tax_label', e.target.value)}
                    placeholder="e.g. VAT"
                    className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Cashier Max Discount (%)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  value={form.cashier_max_discount_pct}
                  onChange={(e) => updateField('cashier_max_discount_pct', e.target.value)}
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-900 focus:border-indigo-600 focus:outline-none"
                />
                <p className="mt-1 text-[11px] text-slate-500">
                  Maximum invoice discount percentage a Cashier can apply at POS (0.00 to 100.00).
                </p>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="min-h-[44px] inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs sm:text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  <Save className="h-4 w-4" />
                  <span>{updateMutation.isPending ? 'Saving...' : 'Save Tax & POS Rules'}</span>
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* TAB 2: Manager Permissions */}
      {activeTab === 'managers' && canManageShop && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 shadow-sm max-w-2xl">
          {isLoadingSettings ? (
            <div className="py-8 text-center text-xs text-slate-500">Loading shop settings...</div>
          ) : isSettingsError || !form ? (
            <div className="text-xs text-red-600">Failed to load shop settings.</div>
          ) : (
            <form onSubmit={handleSaveManagers} className="space-y-4">
              <div className="divide-y divide-slate-100">
                {MANAGER_TOGGLES.map((toggle) => {
                  const checked = form[toggle.key];
                  return (
                    <label
                      key={toggle.key}
                      className="flex items-start justify-between gap-4 py-3.5 cursor-pointer"
                    >
                      <div>
                        <p className="text-sm font-bold text-slate-900">{toggle.label}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{toggle.description}</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => updateField(toggle.key, e.target.checked)}
                        className="mt-1 h-5 w-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-600 shrink-0 cursor-pointer"
                      />
                    </label>
                  );
                })}
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="min-h-[44px] inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs sm:text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  <Save className="h-4 w-4" />
                  <span>
                    {updateMutation.isPending ? 'Saving...' : 'Save Manager Permissions'}
                  </span>
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* TAB 3: Audit Logs */}
      {activeTab === 'audit' && canViewAudit && (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              type="text"
              value={actionInput}
              onChange={(e) => {
                setActionInput(e.target.value);
                setAuditPage(1);
              }}
              placeholder="Filter by action (e.g. INVOICE_VOIDED)..."
              className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none"
            />
            <input
              type="date"
              aria-label="Audit date from"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setAuditPage(1);
              }}
              className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-700 focus:border-indigo-600 focus:outline-none"
            />
            <input
              type="date"
              aria-label="Audit date to"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setAuditPage(1);
              }}
              className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-700 focus:border-indigo-600 focus:outline-none"
            />
          </div>

          {isAuditError && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>Failed to load audit logs.</span>
            </div>
          )}

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            {isLoadingAudit && auditLogs.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400">Loading audit logs...</div>
            ) : auditLogs.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400">
                No audit log entries matched your filters.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs divide-y divide-slate-100">
                  <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                    <tr>
                      <th className="py-3 pl-4 pr-3">Timestamp</th>
                      <th className="py-3 px-3">Actor</th>
                      <th className="py-3 px-3">Action</th>
                      <th className="py-3 px-3">Target</th>
                      <th className="py-3 pr-4 pl-3 text-right">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {auditLogs.map((log) => {
                      const isExpanded = expandedLogId === log.public_id;
                      return (
                        <React.Fragment key={log.public_id}>
                          <tr className="hover:bg-slate-50/70">
                            <td className="py-3 pl-4 pr-3 text-slate-500 whitespace-nowrap">
                              {new Date(log.created_at).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 font-mono font-semibold text-slate-800">
                              {log.actor_username || 'system'}
                            </td>
                            <td className="py-3 px-3">
                              <span className="inline-flex rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 text-[10px] font-bold text-indigo-800">
                                {log.action}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-slate-600">
                              <span className="font-semibold">{log.target_model}</span>
                              {log.target_id && (
                                <span className="block font-mono text-[10px] text-slate-400 truncate max-w-[160px]">
                                  {log.target_id}
                                </span>
                              )}
                            </td>
                            <td className="py-3 pr-4 pl-3 text-right">
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedLogId(isExpanded ? null : log.public_id)
                                }
                                className="inline-flex min-h-[44px] items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                              >
                                <span>{isExpanded ? 'Hide' : 'View'}</span>
                                {isExpanded ? (
                                  <ChevronUp className="h-3.5 w-3.5" />
                                ) : (
                                  <ChevronDown className="h-3.5 w-3.5" />
                                )}
                              </button>
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr className="bg-slate-50">
                              <td colSpan={5} className="p-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px]">
                                  <div>
                                    <p className="font-bold uppercase text-slate-500 mb-1">
                                      Before State
                                    </p>
                                    <pre className="rounded-lg border border-slate-200 bg-white p-2.5 overflow-x-auto text-slate-700">
                                      {JSON.stringify(log.before_state, null, 2)}
                                    </pre>
                                  </div>
                                  <div>
                                    <p className="font-bold uppercase text-slate-500 mb-1">
                                      After State
                                    </p>
                                    <pre className="rounded-lg border border-slate-200 bg-white p-2.5 overflow-x-auto text-slate-700">
                                      {JSON.stringify(log.after_state, null, 2)}
                                    </pre>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination Footer */}
            <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600">
              <span>
                Showing <span className="font-semibold text-slate-800">{auditLogs.length}</span> of{' '}
                <span className="font-semibold text-slate-800">{auditTotal}</span> entries (Page{' '}
                {auditPage})
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={!auditHasPrev || isLoadingAudit}
                  onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
                  className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 cursor-pointer"
                >
                  <ChevronLeft className="h-4 w-4" />
                  <span>Previous</span>
                </button>
                <button
                  type="button"
                  disabled={!auditHasNext || isLoadingAudit}
                  onClick={() => setAuditPage((p) => p + 1)}
                  className="inline-flex min-h-[44px] items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 py-2 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 cursor-pointer"
                >
                  <span>Next</span>
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
