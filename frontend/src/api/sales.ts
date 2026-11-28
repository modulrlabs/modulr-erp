import { apiClient } from './client';
import type { CheckoutPayload, Customer, InvoiceResponse, PaginatedResponse } from '../types/erp';

export async function getCustomers(
  pageSize = 100
): Promise<PaginatedResponse<Customer>> {
  const response = await apiClient.get<PaginatedResponse<Customer>>('/sales/customers/', {
    params: { page_size: pageSize },
  });
  return response.data;
}

export async function createInvoice(
  payload: CheckoutPayload,
  idempotencyKey: string
): Promise<InvoiceResponse> {
  const response = await apiClient.post<InvoiceResponse>('/sales/invoices/', payload, {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });
  return response.data;
}
