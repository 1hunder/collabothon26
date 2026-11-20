import { Outlet } from 'react-router-dom';
import { ToastProvider } from './Toast';

export default function AppFrame(): React.JSX.Element {
  return (
    <div className="mx-auto min-h-dvh w-full max-w-[430px] bg-warm text-petrol">
      <ToastProvider>
        <Outlet />
      </ToastProvider>
    </div>
  );
}
