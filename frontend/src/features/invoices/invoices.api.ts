import { apiClient } from '../../api/client';
import type {
  InvoiceResponse,
  InvoiceStatus,
  PaginatedResponse,
  PaymentMethod,
  SalesReturnCreatePayload,
  SalesReturnResponse,
} from '../../types/erp';

export interface InvoiceQueryParams {
  page?: number;
  page_size?: number;
  status?: InvoiceStatus | '';
  payment_method?: PaymentMethod | '';
  date_from?: string;
  date_to?: string;
  search?: string;
  ordering?: string;
}

export async function getInvoices(
  params: InvoiceQueryParams = {}
): Promise<PaginatedResponse<InvoiceResponse>> {
  const cleanParams: Record<string, string | number> = {};
  if (params.page) cleanParams.page = params.page;
  if (params.page_size) cleanParams.page_size = params.page_size;
  if (params.status) cleanParams.status = params.status;
  if (params.payment_method) cleanParams.payment_method = params.payment_method;
  if (params.date_from) cleanParams.date_from = params.date_from;
  if (params.date_to) cleanParams.date_to = params.date_to;
  if (params.search?.trim()) cleanParams.search = params.search.trim();
  if (params.ordering) cleanParams.ordering = params.ordering;

  const response = await apiClient.get<PaginatedResponse<InvoiceResponse>>('/sales/invoices/', {
    params: cleanParams,
  });
  return response.data;
}

export async function getInvoiceDetail(publicId: string): Promise<InvoiceResponse> {
  const response = await apiClient.get<InvoiceResponse>(`/sales/invoices/${publicId}/`);
  return response.data;
}

export async function voidInvoice(publicId: string, reason: string): Promise<InvoiceResponse> {
  const response = await apiClient.post<InvoiceResponse>(`/sales/invoices/${publicId}/void/`, {
    reason,
  });
  return response.data;
}

export async function returnInvoiceItems(
  publicId: string,
  payload: SalesReturnCreatePayload
): Promise<SalesReturnResponse> {
  const response = await apiClient.post<SalesReturnResponse>(
    `/sales/invoices/${publicId}/return/`,
    payload
  );
  return response.data;
}
