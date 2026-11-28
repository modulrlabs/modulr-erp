import { apiClient } from '../../api/client';
import type {
  CreatePDChequePayload,
  PaginatedResponse,
  PDCheque,
  PDChequeStatus,
  UpdatePDChequeStatusPayload,
} from '../../types/erp';

export interface PDChequeQueryParams {
  page?: number;
  page_size?: number;
  status?: PDChequeStatus | '';
  search?: string;
  due_from?: string;
  due_to?: string;
  ordering?: string;
}

export async function getPDCheques(
  params: PDChequeQueryParams = {}
): Promise<PaginatedResponse<PDCheque>> {
  const cleanParams: Record<string, string | number> = {};
  if (params.page) cleanParams.page = params.page;
  if (params.page_size) cleanParams.page_size = params.page_size;
  if (params.status) cleanParams.status = params.status;
  if (params.search?.trim()) cleanParams.search = params.search.trim();
  if (params.due_from) cleanParams.due_from = params.due_from;
  if (params.due_to) cleanParams.due_to = params.due_to;
  if (params.ordering) cleanParams.ordering = params.ordering;

  const response = await apiClient.get<PaginatedResponse<PDCheque>>('/sales/pd-cheques/', {
    params: cleanParams,
  });
  return response.data;
}

export async function getUpcomingPDCheques(): Promise<PaginatedResponse<PDCheque>> {
  const response = await apiClient.get<PaginatedResponse<PDCheque>>(
    '/sales/pd-cheques/upcoming/',
    {
      params: { page_size: 100 },
    }
  );
  return response.data;
}

export async function createPDCheque(payload: CreatePDChequePayload): Promise<PDCheque> {
  const response = await apiClient.post<PDCheque>('/sales/pd-cheques/', payload);
  return response.data;
}

export async function updatePDChequeStatus(
  publicId: string,
  payload: UpdatePDChequeStatusPayload
): Promise<PDCheque> {
  const response = await apiClient.patch<PDCheque>(`/sales/pd-cheques/${publicId}/`, payload);
  return response.data;
}
