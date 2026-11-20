import { Outlet } from 'react-router-dom';
import TabBar from './TabBar';
import TopBar from './TopBar';

export default function ShellLayout(): React.JSX.Element {
  return (
    <>
      <TopBar />
      <main className="pb-[calc(64px+env(safe-area-inset-bottom))]">
        <Outlet />
      </main>
      <TabBar />
    </>
  );
}
