'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { GoogleLogin } from '@react-oauth/google';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';
import { Code } from '@/lib/core/Constants';

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const res = await Fetch.post<any>('/api/auth/signup', {
        username,
        email,
        password,
        confirmPassword,
      });
      if (res.data.code === Code.Success) {
        Cookie.set('access_token', res.data.data.token);
        router.push('/humanizer');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Registration failed');
    }
    setLoading(false);
  };

  const handleGoogleSuccess = async (credentialResponse: any) => {
    try {
      const res = await Fetch.post<any>('/api/auth/google', {
        credential: credentialResponse.credential,
      });
      if (res.data.code === Code.Success) {
        Cookie.set('access_token', res.data.data.token);
        router.push('/humanizer');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Google login failed');
    }
  };

  return (
    <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule">
      <h1 className="font-serif text-3xl text-ink mb-2">Create account</h1>
      <p className="text-ink-muted mb-6">Start writing better with Margin</p>

      <form onSubmit={handleRegister} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Full name</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="Jane Smith"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="you@university.edu"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="At least 6 characters"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Confirm password</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="Repeat your password"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-dark transition disabled:opacity-50"
        >
          {loading ? 'Creating account...' : 'Create account'}
        </button>
      </form>

      <div className="flex items-center gap-3 my-5">
        <div className="flex-1 h-px bg-rule" />
        <span className="text-xs text-ink-muted">or</span>
        <div className="flex-1 h-px bg-rule" />
      </div>

      <div className="flex justify-center">
        <GoogleLogin onSuccess={handleGoogleSuccess} onError={() => toast.error('Google login failed')} />
      </div>

      <p className="text-center text-sm text-ink-muted mt-6">
        Already have an account?{' '}
        <Link href="/login" className="text-primary font-medium">Sign in</Link>
      </p>
    </div>
  );
}
