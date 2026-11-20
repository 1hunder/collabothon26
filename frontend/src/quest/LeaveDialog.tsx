interface LeaveDialogProps {
  onLeave: () => void;
  onStay: () => void;
}

export default function LeaveDialog({ onLeave, onStay }: LeaveDialogProps): React.JSX.Element {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4 pt-[env(safe-area-inset-top)]">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="leave-dialog-text"
        className="w-full max-w-[360px] rounded-2xl border border-quest-gilt bg-quest-lapis p-5 font-quest text-quest-vellum shadow-xl"
      >
        <p id="leave-dialog-text" className="mb-4 text-base font-semibold">
          Leave the quest? You can continue where you left off.
        </p>
        <div className="flex gap-3">
          <button type="button" onClick={onLeave} className="min-h-11 flex-1 rounded-full border border-quest-vellum-dim px-4 font-quest-sans font-semibold">
            Leave
          </button>
          <button type="button" onClick={onStay} className="min-h-11 flex-1 rounded-full bg-quest-verdigris px-4 font-quest-sans font-semibold text-quest-vellum">
            Stay
          </button>
        </div>
      </div>
    </div>
  );
}
