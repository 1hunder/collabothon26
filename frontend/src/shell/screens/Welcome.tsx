import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScanFace } from 'lucide-react';
import Logo from '../Logo';
import FaceIdAnimation from '../components/FaceIdAnimation';
import type { FaceIdPhase } from '../components/FaceIdAnimation';
import { useSession } from '../lib/session';

const checkAtMs = 1100;
const unlockAtMs = 1500;

export default function Welcome(): React.JSX.Element {
  const navigate = useNavigate();
  const { unlock } = useSession();
  const [phase, setPhase] = useState<FaceIdPhase | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((id) => window.clearTimeout(id));
  }, []);

  function start(): void {
    if (phase !== null) return;
    setPhase('scanning');
    timers.current.push(
      window.setTimeout(() => setPhase('done'), checkAtMs),
      window.setTimeout(() => {
        unlock();
        navigate('/overview', { replace: true });
      }, unlockAtMs),
    );
  }

  return (
    <main className="flex min-h-[calc(100dvh-2rem)] flex-col pt-[env(safe-area-inset-top)] items-center justify-center gap-8 px-6 text-center">
      <Logo className="h-8" />
      <h1 className="text-2xl font-bold">Welcome back, Lena</h1>
      <div className="flex h-20 items-center justify-center">
        {phase !== null && <FaceIdAnimation phase={phase} />}
      </div>
      <button
        type="button"
        onClick={start}
        disabled={phase !== null}
        className="inline-flex items-center gap-2 rounded-pill bg-petrol px-8 py-4 text-base font-medium text-white disabled:opacity-60"
      >
        <ScanFace aria-hidden="true" className="h-5 w-5" />
        Unlock with Face ID
      </button>
    </main>
  );
}
