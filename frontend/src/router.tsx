import { lazy } from 'react';
import { createBrowserRouter, Navigate, Outlet, useSearchParams } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth';
import { Layout } from '@/components/Layout';
import { SocketProvider } from '@/providers/SocketProvider';

const Login = lazy(() => import('@/pages/Login'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const Pipelines = lazy(() => import('@/pages/Pipelines'));
const Glossaries = lazy(() => import('@/pages/Glossaries'));
const Admin = lazy(() => import('@/pages/Admin'));
const Proofread = lazy(() => import('@/pages/Proofread'));
// v5-A3 — 5 new profile pages (replacing legacy AsrProfiles + MtProfiles)
const LLMProfiles = lazy(() => import('@/pages/LLMProfiles'));
const TranscribeProfiles = lazy(() => import('@/pages/TranscribeProfiles'));
const TranslatorProfiles = lazy(() => import('@/pages/TranslatorProfiles'));
const RefinerProfiles = lazy(() => import('@/pages/RefinerProfiles'));
const VerifierProfiles = lazy(() => import('@/pages/VerifierProfiles'));
// Phase 2 — Console feature-flagged page (VITE_CONSOLE=1 env + ?console=1 query)
const Console = lazy(() => import('@/pages/Console').then(m => ({ default: m.Console })));

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
 * ConsoleGate — feature-flag guard for /console.
 * Both VITE_CONSOLE=1 env var AND ?console=1 query param must be present.
 * Missing either redirects to /.
 */
function ConsoleGate() {
  const [params] = useSearchParams();
  const envEnabled = import.meta.env.VITE_CONSOLE === '1';
  const queryEnabled = params.get('console') === '1';
  if (!envEnabled || !queryEnabled) return <Navigate to="/" replace />;
  return <Console />;
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
      // v5-A3 — 5 new profile pages render their own full-page Bold layout —
      // same pattern as Dashboard + Proofread.
      { path: 'llm_profiles', element: <LLMProfiles /> },
      { path: 'transcribe_profiles', element: <TranscribeProfiles /> },
      { path: 'translator_profiles', element: <TranslatorProfiles /> },
      { path: 'refiner_profiles', element: <RefinerProfiles /> },
      { path: 'verifier_profiles', element: <VerifierProfiles /> },
      // Phase 2 — Console feature-flagged route (no Layout shell, same pattern
      // as Dashboard + Proofread + v5 profile pages). ConsoleGate enforces both
      // VITE_CONSOLE=1 env AND ?console=1 query param; missing either → /.
      { path: 'console', element: <ConsoleGate /> },
      // v5-A3 — legacy paths redirect to v5 equivalents (backward-compat for
      // bookmarks + external links + Sunset 2026-12-31 from v5-A1 headers).
      {
        path: 'asr_profiles',
        element: <Navigate to="/transcribe_profiles" replace />,
      },
      {
        path: 'mt_profiles',
        element: <Navigate to="/refiner_profiles" replace />,
      },
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
