import { apiClient } from '../../api/client';
import type {
  CreateCustomerPayload,
  CreditPaymentPayload,
  CreditPaymentResponse,
  Customer,
  PaginatedResponse,
} from '../../types/erp';

export interface CustomerQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
  has_credit?: boolean;
  ordering?: string;
}

export async function getCustomers(
  params: CustomerQueryParams = {}
): Promise<PaginatedResponse<Customer>> {
  const cleanParams: Record<string, string | number | boolean> = {};
  if (params.page) cleanParams.page = params.page;
  if (params.page_size) cleanParams.page_size = params.page_size;
  if (params.search?.trim()) cleanParams.search = params.search.trim();
  if (params.has_credit !== undefined) cleanParams.has_credit = params.has_credit;
  if (params.ordering) cleanParams.ordering = params.ordering;

  const response = await apiClient.get<PaginatedResponse<Customer>>('/sales/customers/', {
    params: cleanParams,
  });
  return response.data;
}

export async function createCustomer(payload: CreateCustomerPayload): Promise<Customer> {
  const response = await apiClient.post<Customer>('/sales/customers/', payload);
  return response.data;
}

export async function deleteCustomer(publicId: string): Promise<void> {
  await apiClient.delete(`/sales/customers/${publicId}/`);
}

export async function recordCreditPayment(
  payload: CreditPaymentPayload
): Promise<CreditPaymentResponse> {
  const response = await apiClient.post<CreditPaymentResponse>('/sales/credit-payments/', payload);
  return response.data;
}
