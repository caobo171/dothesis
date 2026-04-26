'use client';

import React, { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

function WaitVerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get('email');
  const [resending, setResending] = useState(false);

  const handleResend = async () => {
    if (!email) return;
    setResending(true);
    try {
      const res = await Fetch.postWithAccessToken<any>('/api/auth/resend.email', { email });
      if (res.data.code === Code.Success) {
        toast.success('Verification email sent');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Failed to resend email');
    }
    setResending(false);
  };

  return (
    <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule text-center">
      <div className="flex justify-center mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-14 h-14 text-primary">
          <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
        </svg>
      </div>

      <h1 className="font-serif text-2xl text-ink mb-2">Check your email</h1>

      <p className="text-sm text-ink-muted mb-6">
        DoThesis has sent an email to{' '}
        <span className="text-primary font-medium">
          {decodeURIComponent(email ?? '')}
        </span>
        . Click the link in the email to verify your account.
      </p>

      <div className="flex justify-center gap-3">
        <button
          onClick={handleResend}
          disabled={resending}
          className="px-5 py-2.5 rounded-lg border border-rule text-sm font-medium text-ink-soft hover:bg-canvas transition disabled:opacity-50"
        >
          {resending ? 'Sending...' : 'Resend email'}
        </button>

        <button
          onClick={() => router.push('/login')}
          className="px-5 py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-dark transition"
        >
          Back to login
        </button>
      </div>
    </div>
  );
}

export default function WaitVerifyPage() {
  return (
    <Suspense>
      <WaitVerifyContent />
    </Suspense>
  );
}
