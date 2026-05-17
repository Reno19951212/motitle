import { lazy } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth';
import { Layout } from '@/components/Layout';

const Login = lazy(() => import('@/pages/Login'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const Pipelines = lazy(() => import('@/pages/Pipelines'));
const AsrProfiles = lazy(() => import('@/pages/AsrProfiles'));
const MtProfiles = lazy(() => import('@/pages/MtProfiles'));
const Glossaries = lazy(() => import('@/pages/Glossaries'));
const Admin = lazy(() => import('@/pages/Admin'));
const Proofread = lazy(() => import('@/pages/Proofread'));

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
