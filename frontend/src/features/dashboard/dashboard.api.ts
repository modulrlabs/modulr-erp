import { apiClient } from '../../api/client';
import type { DashboardSummaryResponse } from '../../types/erp';

export async function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  const response = await apiClient.get<DashboardSummaryResponse>('/dashboard/summary/');
  return response.data;
}
