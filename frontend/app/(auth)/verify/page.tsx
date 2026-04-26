'use client';

import React, { Suspense, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWRImmutable from 'swr/immutable';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

function VerifyContent() {
  const router = useRouter();
  const token = useSearchParams().get('token');

  const { isLoading, data, error } = useSWRImmutable(
    token ? ['/api/auth/verify', { token }] : null,
    Fetch.getFetcher.bind(Fetch)
  );

  const result = useMemo(() => {
    if (!data) return null;
    const res = (data as any)?.data;
    if (res?.code === Code.Success) {
      return { success: true, username: res.data?.username };
    }
    return { success: false, message: res?.message || 'Verification failed' };
  }, [data, error]);

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule text-center">
        <div className="flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (!result || !result.success) {
    return (
      <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule text-center">
        <div className="flex justify-center mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-14 h-14 text-red-500">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.182 16.318A4.486 4.486 0 0 0 12.016 15a4.486 4.486 0 0 0-3.198 1.318M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z" />
          </svg>
        </div>

        <h1 className="font-serif text-2xl text-ink mb-2">Verification Failed</h1>

        <p className="text-sm text-ink-muted mb-6">
          {result?.message || 'An error occurred during account verification.'}<br />
          Please check your email and try again.
        </p>

        <button
          onClick={() => router.push('/login')}
          className="px-5 py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-dark transition"
        >
          Back to login
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule text-center">
      <div className="flex justify-center mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-14 h-14 text-green-500">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 0 1-1.043 3.296 3.745 3.745 0 0 1-3.296 1.043A3.745 3.745 0 0 1 12 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 0 1-3.296-1.043 3.745 3.745 0 0 1-1.043-3.296A3.745 3.745 0 0 1 3 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 0 1 1.043-3.296 3.746 3.746 0 0 1 3.296-1.043A3.746 3.746 0 0 1 12 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 0 1 3.296 1.043 3.745 3.745 0 0 1 1.043 3.296A3.745 3.745 0 0 1 21 12Z" />
        </svg>
      </div>

      <h1 className="font-serif text-2xl text-ink mb-2">
        Welcome <span className="text-primary">{result.username}</span>
      </h1>

      <p className="text-sm text-ink-muted mb-6">
        Congratulations! Your account has been<br />
        successfully verified.
      </p>

      <button
        onClick={() => router.push('/login')}
        className="px-5 py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-dark transition"
      >
        Start using DoThesis
      </button>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense>
      <VerifyContent />
    </Suspense>
  );
}
