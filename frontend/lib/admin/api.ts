// frontend/lib/admin/api.ts
//
// Thin wrapper around the existing Fetch helper for admin endpoints.
// Centralizing this gives one place to add interceptors (e.g., 403 redirects)
// in a follow-up without touching every page.

import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';

export type AdminResponse<T = any> = {
  code: number;
  data?: T;
  message?: string;
};

const withToken = (params: Record<string, any> = {}) => ({
  ...params,
  access_token: Cookie.fromDocument('access_token'),
});

export const AdminApi = {
  // SWR-friendly fetcher for admin endpoints. Pass this EXPLICITLY as the second
  // argument to useSWR — e.g. useSWR(['/api/admin/users', { page: 1 }], AdminApi.fetcher).
  // The global SWRConfig fetcher (set in app/layout.tsx) handles the same shape, so
  // omitting AdminApi.fetcher here will silently work BUT bypass any 403/redirect
  // interceptors added later. Always pass it explicitly to keep the interception path live.
  fetcher: async (key: string | [string, Record<string, any> | undefined]) => {
    const [url, params] = typeof key === 'string' ? [key, undefined] : key;
    const res = await Fetch.post<AdminResponse>(url, withToken(params));
    return res.data as AdminResponse;
  },

  // For mutations from event handlers.
  post: async <T = any>(url: string, params: Record<string, any> = {}) => {
    const res = await Fetch.post<AdminResponse<T>>(url, withToken(params));
    return res.data as AdminResponse<T>;
  },
};

export default AdminApi;
