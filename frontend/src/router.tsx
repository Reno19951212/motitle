import { lazy } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth';
import { Layout } from '@/components/Layout';
import { SocketProvider } from '@/providers/SocketProvider';

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

/**
 * AuthenticatedShell — wraps all authenticated routes with SocketProvider.
 * Dashboard uses its own full-page Bold layout (no Layout shell), while other
 * pages still use Layout (TopBar + SideNav). Both share this SocketProvider.
 * Choice: option (b) from the dispatch spec — separate router config where
 * Dashboard bypasses Layout. SocketProvider is lifted here so Dashboard can
 * call useSocket() without needing to nest its own provider.
 */
function AuthenticatedShell() {
  return (
    <SocketProvider>
      <Outlet />
    </SocketProvider>
  );
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AuthenticatedShell />
      </RequireAuth>
    ),
    children: [
      // Dashboard renders its own full-page Bold layout — no Layout shell
      { index: true, element: <Dashboard /> },
      // Proofread (iter 1 of Bold redesign) also renders its own full-page
      // Bold layout — no Layout shell. Must sit outside the <Layout/> branch
      // so the b-rail + b-topbar are not nested inside TopBar + SideNav.
      { path: 'proofread/:fileId', element: <Proofread /> },
      // AsrProfiles (iter 2 of Bold redesign) renders its own full-page Bold
      // layout — no Layout shell. Same pattern as Dashboard + Proofread.
      { path: 'asr_profiles', element: <AsrProfiles /> },
      // MtProfiles (iter 3 of Bold redesign) renders its own full-page Bold
      // layout — no Layout shell. Same pattern as Dashboard + Proofread +
      // AsrProfiles.
      { path: 'mt_profiles', element: <MtProfiles /> },
      // Glossaries (iter 4 of Bold redesign) renders its own full-page Bold
      // layout — no Layout shell. Same pattern as Dashboard + Proofread +
      // AsrProfiles + MtProfiles.
      { path: 'glossaries', element: <Glossaries /> },
      // Admin (iter 5 of Bold redesign — FINAL) renders its own full-page
      // Bold layout — no Layout shell. Same pattern as iters 1-4.
      {
        path: 'admin',
        element: (
          <RequireAdmin>
            <Admin />
          </RequireAdmin>
        ),
      },
      // All other pages use the existing Layout (TopBar + SideNav)
      {
        element: <Layout />,
        children: [
          { path: 'pipelines', element: <Pipelines /> },
        ],
      },
    ],
  },
]);
