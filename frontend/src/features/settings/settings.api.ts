import { apiClient } from '../../api/client';
import type {
  AuditLogEntry,
  PaginatedResponse,
  ShopSettings,
  UpdateShopSettingsPayload,
} from '../../types/erp';

export interface AuditLogQueryParams {
  page?: number;
  page_size?: number;
  action?: string;
  actor__public_id?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export async function getShopSettings(): Promise<ShopSettings> {
  const response = await apiClient.get<ShopSettings>('/core/shop-settings/');
  return response.data;
}

export async function updateShopSettings(
  payload: UpdateShopSettingsPayload
): Promise<ShopSettings> {
  const response = await apiClient.patch<ShopSettings>('/core/shop-settings/', payload);
  return response.data;
}

export async function getAuditLogs(
  params: AuditLogQueryParams = {}
): Promise<PaginatedResponse<AuditLogEntry>> {
  const cleanParams: Record<string, string | number> = {};
  if (params.page) cleanParams.page = params.page;
  if (params.page_size) cleanParams.page_size = params.page_size;
  if (params.action?.trim()) cleanParams.action = params.action.trim();
  if (params.actor__public_id?.trim()) cleanParams.actor__public_id = params.actor__public_id.trim();
  if (params.date_from) cleanParams.date_from = params.date_from;
  if (params.date_to) cleanParams.date_to = params.date_to;
  if (params.search?.trim()) cleanParams.search = params.search.trim();

  const response = await apiClient.get<PaginatedResponse<AuditLogEntry>>('/core/audit-logs/', {
    params: cleanParams,
  });
  return response.data;
}
