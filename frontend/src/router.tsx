import { createBrowserRouter, Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth';
import { Layout } from '@/components/Layout';
import Login from '@/pages/Login';
import Dashboard from '@/pages/Dashboard';
import Pipelines from '@/pages/Pipelines';
import AsrProfiles from '@/pages/AsrProfiles';
import MtProfiles from '@/pages/MtProfiles';
import Glossaries from '@/pages/Glossaries';
import Admin from '@/pages/Admin';
import Proofread from '@/pages/Proofread';

function RequireAuth({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'pipelines', element: <Pipelines /> },
      { path: 'asr_profiles', element: <AsrProfiles /> },
      { path: 'mt_profiles', element: <MtProfiles /> },
      { path: 'glossaries', element: <Glossaries /> },
      {
        path: 'admin',
        element: (
          <RequireAdmin>
            <Admin />
          </RequireAdmin>
        ),
      },
      { path: 'proofread/:fileId', element: <Proofread /> },
    ],
  },
]);
