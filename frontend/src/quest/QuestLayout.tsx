import { ArrowLeft, X } from 'lucide-react';
import { useState } from 'react';
import { Outlet, useBlocker, useLocation, useNavigate } from 'react-router-dom';
import './fonts';
import { VoiceToggle } from '../voice';
import LeaveDialog from './LeaveDialog';
import { isQuestFinished } from './questStore';
import { HERO_CLASS_PATH, type QuestEntryState } from './setupNavigation';
import { SheetOpenContext } from './sheetOpen';

function isQuestPath(pathname: string): boolean {
  return pathname === "/quest" || pathname.startsWith("/quest/");
}

export default function QuestLayout(): React.JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      !isQuestFinished() &&
      isQuestPath(currentLocation.pathname) &&
      !isQuestPath(nextLocation.pathname),
  );

  const [sheetOpen, setSheetOpen] = useState(false);
  const entry = location.state as QuestEntryState | null;
  const onDisclosure = location.pathname === '/quest/disclosure';
  const inSetup = onDisclosure || location.pathname === '/quest/hero/new' || location.pathname === HERO_CLASS_PATH;

  const back = (): void => {
    if (onDisclosure && entry?.chooseClass) {
      void navigate(HERO_CLASS_PATH, { replace: true, state: entry });
    } else if (onDisclosure && entry?.newHero) {
      void navigate('/quest/hero/new', { replace: true, state: entry });
    } else {
      void navigate(entry?.origin ?? '/overview', { replace: true });
    }
  };

  const close = (): void => {
    if (location.key === 'default') {
      const origin = entry?.origin ?? '/overview';
      void navigate(origin, { replace: true });
    } else {
      void navigate(-1);
    }
  };

  return (
    <div className="quest-background relative min-h-dvh bg-quest-lapis-deep px-4 font-quest text-quest-vellum pb-[env(safe-area-inset-bottom)] pt-[calc(1rem+env(safe-area-inset-top))]">
      {/* The play screen's dock carries the voice control; a second one here sits under the hero status bar. */}
      {location.pathname === '/quest/play' ? null : (
        <div className="absolute left-3 top-[calc(0.75rem+env(safe-area-inset-top))] flex">
          {inSetup && (
            <button
              type="button"
              aria-label="Back"
              onClick={back}
              className="flex h-11 w-11 items-center justify-center rounded-full text-quest-vellum"
            >
              <ArrowLeft aria-hidden="true" size={24} />
            </button>
          )}
          <VoiceToggle />
        </div>
      )}
      {sheetOpen ? null : (
        <button
          type="button"
          aria-label="Close quest"
          onClick={close}
          className="absolute right-3 top-[calc(0.75rem+env(safe-area-inset-top))] z-20 flex h-11 w-11 items-center justify-center rounded-full text-quest-vellum"
        >
          <X aria-hidden="true" size={24} />
        </button>
      )}
      <main className="pt-10">
        <SheetOpenContext.Provider value={setSheetOpen}>
          <Outlet />
        </SheetOpenContext.Provider>
      </main>
      {blocker.state === "blocked" ? (
        <LeaveDialog
          onLeave={() => blocker.proceed()}
          onStay={() => blocker.reset()}
        />
      ) : null}
    </div>
  );
}
