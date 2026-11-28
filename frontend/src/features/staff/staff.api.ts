import { apiClient } from '../../api/client';
import type {
  CreateStaffPayload,
  CreateStaffResponse,
  PaginatedResponse,
  ResetPasswordResponse,
  StaffMember,
  UserRole,
} from '../../types/erp';

export interface StaffQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
}

export async function getStaff(
  params: StaffQueryParams = {}
): Promise<PaginatedResponse<StaffMember>> {
  const cleanParams: Record<string, string | number> = {};
  if (params.page) cleanParams.page = params.page;
  if (params.page_size) cleanParams.page_size = params.page_size;
  if (params.search?.trim()) cleanParams.search = params.search.trim();

  const response = await apiClient.get<PaginatedResponse<StaffMember>>('/staff/', {
    params: cleanParams,
  });
  return response.data;
}

export async function createStaff(payload: CreateStaffPayload): Promise<CreateStaffResponse> {
  const response = await apiClient.post<CreateStaffResponse>('/staff/', payload);
  return response.data;
}

export async function updateStaffRole(
  publicId: string,
  role: UserRole
): Promise<StaffMember> {
  const response = await apiClient.patch<StaffMember>(`/staff/${publicId}/`, { role });
  return response.data;
}

export async function deactivateStaff(publicId: string): Promise<StaffMember> {
  const response = await apiClient.post<StaffMember>(`/staff/${publicId}/deactivate/`);
  return response.data;
}

export async function reactivateStaff(publicId: string): Promise<StaffMember> {
  const response = await apiClient.post<StaffMember>(`/staff/${publicId}/reactivate/`);
  return response.data;
}

export async function resetStaffPassword(publicId: string): Promise<ResetPasswordResponse> {
  const response = await apiClient.post<ResetPasswordResponse>(
    `/staff/${publicId}/reset-password/`
  );
  return response.data;
}
