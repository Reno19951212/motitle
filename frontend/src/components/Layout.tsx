import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { SideNav } from './SideNav';
import { SocketProvider } from '@/providers/SocketProvider';

export function Layout() {
  return (
    <div className="grid grid-rows-[auto_1fr] grid-cols-[200px_1fr] h-screen">
      <header className="col-span-2 border-b">
        <TopBar />
      </header>
      <aside className="border-r bg-muted/30">
        <SideNav />
      </aside>
      <main className="overflow-auto p-6">
        <SocketProvider>
          <Outlet />
        </SocketProvider>
      </main>
    </div>
  );
}
