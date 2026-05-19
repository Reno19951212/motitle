import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/providers/AuthProvider';
import { router } from '@/router';
import { PageLoader } from '@/components/PageLoader';
import { Toaster } from '@/components/ui/toaster';

export function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<PageLoader />}>
        <RouterProvider router={router} />
      </Suspense>
      <Toaster />
    </AuthProvider>
  );
}
