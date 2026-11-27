import { apiClient } from './client';
import type { Category, PaginatedResponse, Product } from '../types/erp';

export interface ProductQueryParams {
  page?: number;
  page_size?: number;
  search?: string;
  category?: number | string;
  low_stock?: boolean;
  ordering?: string;
}

export interface CreateProductPayload {
  category: number | null;
  name: string;
  barcode: string | null;
  cost_price?: string;
  selling_price: string;
  stock_quantity: string;
  reorder_level: string;
}

export interface CreateCategoryPayload {
  name: string;
  description?: string;
}

export async function getProducts(
  params: ProductQueryParams = {}
): Promise<PaginatedResponse<Product>> {
  const response = await apiClient.get<PaginatedResponse<Product>>('/inventory/products/', {
    params,
  });
  return response.data;
}

export async function getProductByBarcode(code: string): Promise<Product> {
  const response = await apiClient.get<Product>('/inventory/products/by-barcode/', {
    params: { code },
  });
  return response.data;
}

export async function createProduct(payload: CreateProductPayload): Promise<Product> {
  const response = await apiClient.post<Product>('/inventory/products/', payload);
  return response.data;
}

export async function getCategories(
  pageSize = 100
): Promise<PaginatedResponse<Category>> {
  const response = await apiClient.get<PaginatedResponse<Category>>('/inventory/categories/', {
    params: { page_size: pageSize },
  });
  return response.data;
}

export async function createCategory(payload: CreateCategoryPayload): Promise<Category> {
  const response = await apiClient.post<Category>('/inventory/categories/', payload);
  return response.data;
}
