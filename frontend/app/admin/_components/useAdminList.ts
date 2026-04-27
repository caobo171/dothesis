// frontend/app/admin/_components/useAdminList.ts
//
// SWR wrapper for admin list endpoints. Centralizes the list response shape
// so callers don't repeatedly destructure { items, total, page, limit }.
//
// Usage:
//   const { items, total, page, limit, isLoading, mutate } = useAdminList(
//     '/api/admin/users',
//     { q: 'foo', page: 2 }
//   );
//
// IMPORTANT: passes AdminApi.fetcher explicitly so the global SWRConfig fetcher
// is not used. This keeps the future 403-interceptor path live.

import useSWR from 'swr';
import AdminApi from '@/lib/admin/api';

export type AdminList<T> = {
  items: T[];
  total: number;
  page: number;
  limit: number;
};

export function useAdminList<T>(url: string, params: Record<string, any> = {}) {
  const { data, error, isLoading, mutate } = useSWR(
    [url, params],
    AdminApi.fetcher
  );

  const payload = (data as any)?.data as AdminList<T> | undefined;

  return {
    items: payload?.items || [],
    total: payload?.total || 0,
    page: payload?.page || 1,
    limit: payload?.limit || 25,
    isLoading,
    error,
    mutate,
    raw: data,
  };
}

export default useAdminList;
