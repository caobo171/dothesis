import useSWR from 'swr';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { loadProfile } from '@/store/slices/authSlice';
import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';
import { Code } from '@/lib/core/Constants';
import { useCallback, useEffect } from 'react';

export function useMe() {
  const dispatch = useDispatch();

  const { data, error, mutate } = useSWR(
    Cookie.fromDocument('access_token') ? ['/api/me', {}] : null,
    {
      onSuccess: (res: any) => {
        if (res?.code === Code.Success) {
          dispatch(loadProfile(res.data));
        }
      },
    }
  );

  return {
    data: data?.code === Code.Success ? data.data : null,
    error,
    isLoading: !data && !error,
    mutate,
  };
}

export function useReloadMe() {
  const { mutate } = useMe();
  return useCallback(() => mutate(), [mutate]);
}
