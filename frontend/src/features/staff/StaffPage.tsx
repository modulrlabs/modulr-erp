import React, { useState } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  KeyRound,
  RefreshCw,
  Shield,
  UserCheck,
  UserPlus,
  UserX,
  Users,
  X,
} from 'lucide-react';
import { usePermission } from '../../hooks/usePermission';
import { useAuthStore } from '../../stores/authStore';
import type { StaffMember, UserRole } from '../../types/erp';
import {
  createStaff,
  deactivateStaff,
  getStaff,
  reactivateStaff,
  resetStaffPassword,
  updateStaffRole,
} from './staff.api';

const ALL_ROLES: { value: UserRole; label: string }[] = [
  { value: 'CASHIER', label: 'Cashier' },
  { value: 'MANAGER', label: 'Manager' },
  { value: 'INVENTORY_MANAGER', label: 'Inventory Manager' },
  { value: 'ACCOUNTANT', label: 'Accountant' },
  { value: 'OWNER', label: 'Owner' },
];

function getRoleBadgeClass(role: UserRole): string {
  switch (role) {
    case 'OWNER':
      return 'bg-purple-100 text-purple-800 border-purple-200';
    case 'MANAGER':
      return 'bg-indigo-100 text-indigo-800 border-indigo-200';
    case 'INVENTORY_MANAGER':
      return 'bg-teal-100 text-teal-800 border-teal-200';
    case 'ACCOUNTANT':
      return 'bg-amber-100 text-amber-800 border-amber-200';
    case 'CASHIER':
    default:
      return 'bg-blue-100 text-blue-800 border-blue-200';
  }
}

interface OneTimeCredentials {
  username: string;
  temporary_password: string;
  title: string;
}

export const StaffPage: React.FC = () => {
  const { user: currentUser } = useAuthStore();
  const canManageAllStaff = usePermission('staff.manage');
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);

  // Add Staff Modal
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newStaff, setNewStaff] = useState({
    first_name: '',
    last_name: '',
    email: '',
    role: 'CASHIER' as UserRole,
  });
  const [addError, setAddError] = useState<string | null>(null);

  // One-Time Credentials Box (shared by Create & Reset Password)
  const [credentials, setCredentials] = useState<OneTimeCredentials | null>(null);
  const [copied, setCopied] = useState(false);

  // Edit Role Modal
  const [editTarget, setEditTarget] = useState<StaffMember | null>(null);
  const [selectedRole, setSelectedRole] = useState<UserRole>('CASHIER');
  const [editError, setEditError] = useState<string | null>(null);

  // Deactivate / Reactivate Modal
  const [toggleTarget, setToggleTarget] = useState<StaffMember | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  // Reset Password Modal
  const [resetTarget, setResetTarget] = useState<StaffMember | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['staff', { page }],
    queryFn: () => getStaff({ page }),
  });

  const createMutation = useMutation({
    mutationFn: createStaff,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['staff'] });
      setIsAddModalOpen(false);
      setNewStaff({ first_name: '', last_name: '', email: '', role: 'CASHIER' });
      setAddError(null);
      setCopied(false);
      setCredentials({
        username: res.username,
        temporary_password: res.temporary_password,
        title: 'Staff Account Created',
      });
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as Record<string, string | string[]> | undefined;
        if (resp) {
          const firstKey = Object.keys(resp)[0];
          const val = resp[firstKey];
          setAddError(`${firstKey}: ${Array.isArray(val) ? val[0] : val}`);
        } else {
          setAddError('Failed to create staff account.');
        }
      } else {
        setAddError('An unexpected error occurred.');
      }
    },
  });

  const roleMutation = useMutation({
    mutationFn: ({ publicId, role }: { publicId: string; role: UserRole }) =>
      updateStaffRole(publicId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff'] });
      setEditTarget(null);
      setEditError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as { detail?: string; role?: string[] } | undefined;
        setEditError(resp?.detail || resp?.role?.[0] || 'Failed to update staff role.');
      } else {
        setEditError('An unexpected error occurred.');
      }
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ publicId, activate }: { publicId: string; activate: boolean }) =>
      activate ? reactivateStaff(publicId) : deactivateStaff(publicId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff'] });
      setToggleTarget(null);
      setToggleError(null);
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as { detail?: string } | undefined;
        setToggleError(resp?.detail || 'Failed to update staff status.');
      } else {
        setToggleError('An unexpected error occurred.');
      }
    },
  });

  const resetPwdMutation = useMutation({
    mutationFn: (publicId: string) => resetStaffPassword(publicId),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['staff'] });
      setResetTarget(null);
      setResetError(null);
      setCopied(false);
      setCredentials({
        username: res.username,
        temporary_password: res.temporary_password,
        title: 'Temporary Password Reset',
      });
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const resp = err.response?.data as { detail?: string } | undefined;
        setResetError(resp?.detail || 'Failed to reset password.');
      } else {
        setResetError('An unexpected error occurred.');
      }
    },
  });

  const staffList = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasNext = Boolean(data?.next);
  const hasPrevious = Boolean(data?.previous);

  const handleCopyCredentials = async () => {
    if (!credentials) return;
    const text = `Username: ${credentials.username}\nTemporary Password: ${credentials.temporary_password}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Clipboard API may be unavailable in non-HTTPS contexts
    }
  };

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);
    if (!newStaff.first_name.trim()) {
      setAddError('First name is required.');
      return;
    }
    createMutation.mutate({
      first_name: newStaff.first_name.trim(),
      last_name: newStaff.last_name.trim(),
      email: newStaff.email.trim(),
      role: canManageAllStaff ? newStaff.role : 'CASHIER',
    });
  };

  const availableRoles = canManageAllStaff
    ? ALL_ROLES
    : ALL_ROLES.filter((r) => r.value === 'CASHIER');

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            Staff Management
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            {canManageAllStaff
              ? 'Create staff accounts, assign roles, and reset temporary passwords'
              : 'Manage Cashier accounts for your shop'}
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

          <button
            type="button"
            onClick={() => {
              setNewStaff({ first_name: '', last_name: '', email: '', role: 'CASHIER' });
              setAddError(null);
              setIsAddModalOpen(true);
            }}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs sm:text-sm font-bold text-white shadow-sm hover:bg-indigo-700 cursor-pointer"
          >
            <UserPlus className="h-4 w-4" />
            <span>Add Staff</span>
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs sm:text-sm font-medium text-red-700 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>Failed to load staff list. Please try again.</span>
        </div>
      )}

      {/* Staff List Container */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading && staffList.length === 0 ? (
          <div className="py-12 flex flex-col items-center gap-2 text-slate-400">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
            <span className="text-xs">Loading staff accounts...</span>
          </div>
        ) : staffList.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <Users className="h-8 w-8 mx-auto text-slate-300 stroke-[1.5]" />
            <p className="mt-2 text-sm font-semibold text-slate-700">No staff accounts found</p>
          </div>
        ) : (
          <>
            {/* Tablet / Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-left text-xs divide-y divide-slate-100">
                <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                  <tr>
                    <th className="py-3 pl-4 pr-3">Full Name</th>
                    <th className="py-3 px-3">System Username</th>
                    <th className="py-3 px-3 text-center">Role</th>
                    <th className="py-3 px-3 text-center">Status</th>
                    <th className="py-3 pr-4 pl-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {staffList.map((member) => {
                    const isSelf = member.username === currentUser?.username;
                    const canManageTarget = canManageAllStaff || member.role === 'CASHIER';
                    const fullName =
                      `${member.first_name} ${member.last_name}`.trim() || member.username;

                    return (
                      <tr key={member.public_id} className="hover:bg-slate-50/70">
                        <td className="py-3 pl-4 pr-3">
                          <div className="font-bold text-slate-900">
                            {fullName}{' '}
                            {isSelf && (
                              <span className="ml-1 text-[10px] font-semibold text-indigo-600">
                                (You)
                              </span>
                            )}
                          </div>
                          {member.email && (
                            <div className="text-[11px] text-slate-500">{member.email}</div>
                          )}
                        </td>
                        <td className="py-3 px-3 font-mono text-xs text-slate-700">
                          {member.username}
                        </td>
                        <td className="py-3 px-3 text-center">
                          <span
                            className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getRoleBadgeClass(
                              member.role
                            )}`}
                          >
                            {member.role}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-center">
                          {member.is_active ? (
                            <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-700">
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex rounded-full border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold text-slate-600">
                              Inactive
                            </span>
                          )}
                        </td>
                        <td className="py-3 pr-4 pl-3 text-right">
                          {canManageTarget ? (
                            <div className="inline-flex items-center justify-end gap-1.5">
                              {canManageAllStaff && !isSelf && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setEditTarget(member);
                                    setSelectedRole(member.role);
                                    setEditError(null);
                                  }}
                                  className="inline-flex min-h-[44px] items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                                >
                                  <Shield className="h-3.5 w-3.5" />
                                  <span>Role</span>
                                </button>
                              )}

                              <button
                                type="button"
                                onClick={() => {
                                  setResetTarget(member);
                                  setResetError(null);
                                }}
                                className="inline-flex min-h-[44px] items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-amber-50 hover:border-amber-200 hover:text-amber-800 cursor-pointer"
                              >
                                <KeyRound className="h-3.5 w-3.5" />
                                <span>Reset Pwd</span>
                              </button>

                              {!isSelf && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setToggleTarget(member);
                                    setToggleError(null);
                                  }}
                                  className={`inline-flex min-h-[44px] items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-semibold cursor-pointer ${
                                    member.is_active
                                      ? 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100'
                                      : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                                  }`}
                                >
                                  {member.is_active ? (
                                    <>
                                      <UserX className="h-3.5 w-3.5" />
                                      <span>Deactivate</span>
                                    </>
                                  ) : (
                                    <>
                                      <UserCheck className="h-3.5 w-3.5" />
                                      <span>Reactivate</span>
                                    </>
                                  )}
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Stacked Cards */}
            <div className="md:hidden divide-y divide-slate-100">
              {staffList.map((member) => {
                const isSelf = member.username === currentUser?.username;
                const canManageTarget = canManageAllStaff || member.role === 'CASHIER';
                const fullName =
                  `${member.first_name} ${member.last_name}`.trim() || member.username;

                return (
                  <div key={member.public_id} className="p-4 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-bold text-slate-900">
                          {fullName} {isSelf && <span className="text-indigo-600">(You)</span>}
                        </p>
                        <p className="text-xs font-mono text-slate-600">{member.username}</p>
                      </div>
                      <span
                        className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${getRoleBadgeClass(
                          member.role
                        )}`}
                      >
                        {member.role}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-500">{member.email || 'No email'}</span>
                      {member.is_active ? (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                          Active
                        </span>
                      ) : (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                          Inactive
                        </span>
                      )}
                    </div>

                    {canManageTarget && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {canManageAllStaff && !isSelf && (
                          <button
                            type="button"
                            onClick={() => {
                              setEditTarget(member);
                              setSelectedRole(member.role);
                              setEditError(null);
                            }}
                            className="flex-1 min-h-[44px] inline-flex items-center justify-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
                          >
                            <Shield className="h-4 w-4" />
                            <span>Role</span>
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setResetTarget(member);
                            setResetError(null);
                          }}
                          className="flex-1 min-h-[44px] inline-flex items-center justify-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
                        >
                          <KeyRound className="h-4 w-4" />
                          <span>Reset Pwd</span>
                        </button>
                        {!isSelf && (
                          <button
                            type="button"
                            onClick={() => {
                              setToggleTarget(member);
                              setToggleError(null);
                            }}
                            className={`flex-1 min-h-[44px] inline-flex items-center justify-center gap-1 rounded-xl border px-3 py-2 text-xs font-semibold ${
                              member.is_active
                                ? 'border-red-200 bg-red-50 text-red-700'
                                : 'border-emerald-200 bg-emerald-50 text-emerald-700'
                            }`}
                          >
                            {member.is_active ? 'Deactivate' : 'Reactivate'}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Pagination Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-600">
          <span>
            Showing <span className="font-semibold text-slate-800">{staffList.length}</span> of{' '}
            <span className="font-semibold text-slate-800">{totalCount}</span> staff (Page {page})
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

      {/* Add Staff Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Add Staff Account</h2>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              A unique username and one-time temporary password will be generated automatically.
            </p>

            {addError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{addError}</span>
              </div>
            )}

            <form onSubmit={handleAddSubmit} className="space-y-4 text-xs font-medium">
              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  First Name *
                </label>
                <input
                  type="text"
                  required
                  value={newStaff.first_name}
                  onChange={(e) => setNewStaff({ ...newStaff, first_name: e.target.value })}
                  placeholder="e.g. Nimal"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Last Name (Optional)
                </label>
                <input
                  type="text"
                  value={newStaff.last_name}
                  onChange={(e) => setNewStaff({ ...newStaff, last_name: e.target.value })}
                  placeholder="e.g. Silva"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Email (Optional)
                </label>
                <input
                  type="email"
                  value={newStaff.email}
                  onChange={(e) => setNewStaff({ ...newStaff, email: e.target.value })}
                  placeholder="e.g. nimal@shop.lk"
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-bold uppercase tracking-wider mb-1">
                  Role *
                </label>
                <select
                  value={canManageAllStaff ? newStaff.role : 'CASHIER'}
                  disabled={!canManageAllStaff}
                  onChange={(e) => setNewStaff({ ...newStaff, role: e.target.value as UserRole })}
                  className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 disabled:bg-slate-100"
                >
                  {availableRoles.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
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
                  {createMutation.isPending ? 'Creating...' : 'Create Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* One-Time Credentials Modal */}
      {credentials && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-emerald-200 space-y-4">
            <h2 className="text-lg font-bold text-slate-900">{credentials.title}</h2>

            <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs font-semibold text-amber-900">
              Save or share these credentials now. The temporary password will never be shown again.
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase text-slate-500">Username</span>
                <span className="font-mono font-bold text-slate-900">{credentials.username}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase text-slate-500">Temp Password</span>
                <span className="font-mono font-bold text-indigo-700">
                  {credentials.temporary_password}
                </span>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCopyCredentials}
                className="flex-1 min-h-[44px] inline-flex items-center justify-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2 text-xs font-bold text-indigo-700 hover:bg-indigo-100 cursor-pointer"
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                <span>{copied ? 'Copied!' : 'Copy Credentials'}</span>
              </button>
              <button
                type="button"
                onClick={() => setCredentials(null)}
                className="min-h-[44px] rounded-xl bg-slate-900 px-5 py-2 text-xs font-bold text-white hover:bg-slate-800 cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Role Modal */}
      {editTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">
                Change Role for {editTarget.username}
              </h2>
              <button
                type="button"
                onClick={() => setEditTarget(null)}
                className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {editError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{editError}</span>
              </div>
            )}

            <div className="space-y-4">
              <select
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value as UserRole)}
                className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 bg-white focus:border-indigo-600 focus:outline-none"
              >
                {availableRoles.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditTarget(null)}
                  className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={roleMutation.isPending}
                  onClick={() =>
                    roleMutation.mutate({ publicId: editTarget.public_id, role: selectedRole })
                  }
                  className="min-h-[44px] rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  {roleMutation.isPending ? 'Saving...' : 'Save Role'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Deactivate / Reactivate Confirmation Modal */}
      {toggleTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <h2 className="text-base font-bold text-slate-900">
              {toggleTarget.is_active ? 'Deactivate' : 'Reactivate'} {toggleTarget.username}?
            </h2>
            <p className="text-xs text-slate-600">
              {toggleTarget.is_active
                ? 'Deactivating immediately revokes active sessions and blocks login.'
                : 'Reactivating allows this staff member to sign in again.'}
            </p>

            {toggleError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{toggleError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setToggleTarget(null)}
                className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={toggleActiveMutation.isPending}
                onClick={() =>
                  toggleActiveMutation.mutate({
                    publicId: toggleTarget.public_id,
                    activate: !toggleTarget.is_active,
                  })
                }
                className={`min-h-[44px] rounded-xl px-4 py-2 text-xs font-bold text-white disabled:opacity-50 cursor-pointer ${
                  toggleTarget.is_active
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {toggleActiveMutation.isPending
                  ? 'Updating...'
                  : toggleTarget.is_active
                  ? 'Confirm Deactivate'
                  : 'Confirm Reactivate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset Password Confirmation Modal */}
      {resetTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 space-y-4">
            <h2 className="text-base font-bold text-slate-900">
              Reset Password for {resetTarget.username}?
            </h2>
            <p className="text-xs text-slate-600">
              This generates a new one-time temporary password, revokes existing sessions, and forces
              a password change on next login.
            </p>

            {resetError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{resetError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setResetTarget(null)}
                className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={resetPwdMutation.isPending}
                onClick={() => resetPwdMutation.mutate(resetTarget.public_id)}
                className="min-h-[44px] rounded-xl bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50 cursor-pointer"
              >
                {resetPwdMutation.isPending ? 'Resetting...' : 'Reset Password'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
