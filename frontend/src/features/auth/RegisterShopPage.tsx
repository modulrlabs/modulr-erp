import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { AlertCircle, Lock, Mail, MapPin, Phone, Store, User } from 'lucide-react';
import { apiClient, syncAuthMe } from '../../api/client';
import { getDefaultHomeRoute, useAuthStore } from '../../stores/authStore';
import type { RegisterShopPayload, ShopProfile, UserProfile } from '../../types/erp';

export const RegisterShopPage: React.FC = () => {
  const [formData, setFormData] = useState<RegisterShopPayload>({
    shop_name: '',
    address: '',
    phone: '',
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
  });

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!formData.shop_name.trim() || !formData.username.trim() || !formData.password) {
      setErrorMessage('Shop name, username, and password are required.');
      return;
    }

    if (formData.password.length < 8) {
      setErrorMessage('Password must be at least 8 characters long.');
      return;
    }

    try {
      setIsLoading(true);
      const response = await apiClient.post<{
        message: string;
        tokens: { access: string };
        user: UserProfile;
        shop: {
          id: number;
          public_id: string;
          name: string;
          address: string;
          phone: string;
          enable_credit_module: boolean;
          enable_whatsapp_alerts: boolean;
        };
      }>('/auth/register/', formData);

      const { tokens, user, shop } = response.data;

      const normalizedShop: ShopProfile = {
        id: shop.id,
        public_id: shop.public_id,
        name: shop.name,
        address: shop.address,
        phone: shop.phone,
        features: {
          enable_credit_module: shop.enable_credit_module ?? true,
          enable_whatsapp_alerts: shop.enable_whatsapp_alerts ?? true,
        },
      };

      setAuth(user, normalizedShop, tokens.access, [], false);
      await syncAuthMe();
      navigate(getDefaultHomeRoute(user.role), { replace: true });
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const errorData = err.response?.data as Record<string, string | string[]> | undefined;
        if (errorData) {
          const firstKey = Object.keys(errorData)[0];
          const val = errorData[firstKey];
          const msg = Array.isArray(val) ? val[0] : val;
          setErrorMessage(`${firstKey}: ${msg}`);
        } else {
          setErrorMessage('Registration failed. Please check the provided information.');
        }
      } else {
        setErrorMessage('An unexpected error occurred. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col justify-center bg-slate-50 py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-xl">
        <div className="flex justify-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-200">
            <Store className="h-7 w-7" />
          </div>
        </div>
        <h2 className="mt-4 text-center text-2xl font-extrabold tracking-tight text-slate-900">
          Register Your Store on Modulr ERP
        </h2>
        <p className="mt-1 text-center text-sm text-slate-600">
          Create your tenant shop and founder Owner account
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-xl px-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-8 shadow-sm">
          {errorMessage && (
            <div className="mb-6 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50/90 p-4 text-sm text-red-700">
              <AlertCircle className="h-5 w-5 shrink-0 text-red-500 mt-0.5" />
              <div className="leading-relaxed">{errorMessage}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Store Information Section */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-700 border-b border-indigo-100 pb-1.5 mb-3">
                1. Store Information
              </h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Store / Shop Name *
                  </label>
                  <div className="relative rounded-lg shadow-sm">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                      <Store className="h-4 w-4" />
                    </div>
                    <input
                      name="shop_name"
                      type="text"
                      required
                      value={formData.shop_name}
                      onChange={handleChange}
                      placeholder="e.g. City Supermarket"
                      className="block w-full rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Phone Number
                  </label>
                  <div className="relative rounded-lg shadow-sm">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                      <Phone className="h-4 w-4" />
                    </div>
                    <input
                      name="phone"
                      type="text"
                      value={formData.phone}
                      onChange={handleChange}
                      placeholder="e.g. 0112345678"
                      className="block w-full rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Store Address
                  </label>
                  <div className="relative rounded-lg shadow-sm">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                      <MapPin className="h-4 w-4" />
                    </div>
                    <input
                      name="address"
                      type="text"
                      value={formData.address}
                      onChange={handleChange}
                      placeholder="e.g. 123 Galle Road, Colombo"
                      className="block w-full rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Owner Credentials Section */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-700 border-b border-indigo-100 pb-1.5 mb-3">
                2. Owner Account Details
              </h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    First Name
                  </label>
                  <input
                    name="first_name"
                    type="text"
                    value={formData.first_name}
                    onChange={handleChange}
                    placeholder="Jane"
                    className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Last Name
                  </label>
                  <input
                    name="last_name"
                    type="text"
                    value={formData.last_name}
                    onChange={handleChange}
                    placeholder="Doe"
                    className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Username *
                  </label>
                  <div className="relative rounded-lg shadow-sm">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                      <User className="h-4 w-4" />
                    </div>
                    <input
                      name="username"
                      type="text"
                      required
                      value={formData.username}
                      onChange={handleChange}
                      placeholder="e.g. jane_owner"
                      className="block w-full rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Email Address
                  </label>
                  <div className="relative rounded-lg shadow-sm">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                      <Mail className="h-4 w-4" />
                    </div>
                    <input
                      name="email"
                      type="email"
                      value={formData.email}
                      onChange={handleChange}
                      placeholder="jane@example.com"
                      className="block w-full rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                    />
                  </div>
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Password * (Min. 8 characters)
                  </label>
                  <div className="relative rounded-lg shadow-sm">
                    <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                      <Lock className="h-4 w-4" />
                    </div>
                    <input
                      name="password"
                      type="password"
                      required
                      minLength={8}
                      value={formData.password}
                      onChange={handleChange}
                      placeholder="••••••••"
                      className="block w-full rounded-lg border border-slate-300 pl-10 pr-3 py-2 text-sm text-slate-900 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
                    />
                  </div>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2 disabled:opacity-50 transition-colors cursor-pointer"
            >
              {isLoading ? 'Creating Store & Account...' : 'Complete Registration'}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-100 pt-6 text-center">
            <p className="text-xs text-slate-600">
              Already have an account?{' '}
              <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-500">
                Sign In
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
