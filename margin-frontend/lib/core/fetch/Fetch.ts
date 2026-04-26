import axios, { AxiosPromise } from 'axios';
import Cookie from './Cookie';
import { API_URL } from '@/lib/core/Constants';

type AnyObject = Record<string, any>;

class Fetch {
  private __base_url: string = API_URL;

  async postWithAccessToken<ResponseType>(
    url: string,
    params: Object = {},
    context: { access_token: string } | null = null
  ): Promise<AxiosPromise<ResponseType>> {
    return this.post<ResponseType>(url, {
      ...params,
      access_token: context
        ? context.access_token
        : Cookie.fromDocument('access_token'),
    });
  }

  async get<ResponseType>(
    url: string,
    params: any = {}
  ): Promise<AxiosPromise<ResponseType>> {
    return axios.get(`${this.__base_url}${url}`, params);
  }

  async post<ResponseType>(
    url: string,
    params: any = {}
  ): Promise<AxiosPromise<ResponseType>> {
    if (typeof XMLHttpRequest === 'undefined') {
      // @ts-ignore
      return fetch(`${this.__base_url}${url}`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(params),
        cache: 'no-store',
      }).then(async (e) => {
        if (e.status !== 200) {
          return { message: e.statusText, code: 0 };
        }
        return { data: await e.json() };
      });
    }

    if (typeof window !== 'undefined') {
      const form_data = new FormData();
      for (const k in params) {
        if (Array.isArray(params[k])) {
          for (let i = 0; i < params[k].length; i++) {
            form_data.append(`${k}[]`, params[k][i]);
          }
        } else if (params[k] != null && params[k] != undefined) {
          form_data.append(k, params[k]);
        }
      }
      return axios.post(`${this.__base_url}${url}`, form_data);
    }

    return axios.post(`${this.__base_url}${url}`, params);
  }

  async getFetcher(obj: string | [string, AnyObject | undefined | null]) {
    let url: string = typeof obj === 'string' ? obj : '';
    let args: AnyObject | undefined | null;

    if (Array.isArray(obj)) {
      [url, args] = obj;
    }

    const params: AnyObject = { ...args };
    const accessToken = args?.accessToken;

    if (typeof accessToken === 'string') {
      params.access_token = accessToken;
    } else if (typeof accessToken === 'undefined' || accessToken) {
      params.access_token = Cookie.fromDocument('access_token');
    }

    return this.post(url, params);
  }

  async postFetcher(url: string, options: { arg: { payload: AnyObject; accessToken?: boolean | string } }) {
    const { accessToken, payload } = options.arg;

    if (typeof accessToken === 'string') {
      payload.access_token = accessToken;
    } else if (typeof accessToken === 'undefined' || accessToken) {
      payload.access_token = Cookie.fromDocument('access_token');
    }

    return this.post(url, payload);
  }
}

export default new Fetch();
