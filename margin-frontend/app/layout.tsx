'use client';

import './globals.css';
import React from 'react';
import { Provider } from 'react-redux';
import { SWRConfig } from 'swr';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { store } from '@/store/store';
import Fetch from '@/lib/core/fetch/Fetch';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <Provider store={store}>
          <SWRConfig
            value={{
              fetcher: (url: any) => Fetch.getFetcher(url).then((r: any) => r.data),
              revalidateOnFocus: false,
            }}
          >
            <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ''}>
              {children}
              <ToastContainer position="bottom-center" autoClose={3000} />
            </GoogleOAuthProvider>
          </SWRConfig>
        </Provider>
      </body>
    </html>
  );
}
