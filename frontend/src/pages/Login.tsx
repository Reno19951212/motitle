import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';

export default function Login() {
  const user = useAuthStore((s) => s.user);
  if (user) return <Navigate to="/" replace />;
  return <h1 className="text-2xl p-8">Login (T10 implements full form)</h1>;
}
