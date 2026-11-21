interface DisclosureNoteProps {
  onDismiss: () => void;
  pending?: boolean;
}

export default function DisclosureNote({ onDismiss, pending }: DisclosureNoteProps): React.JSX.Element {
  return (
    <section className="rounded-lg border border-quest-gilt bg-quest-lapis p-4 font-quest text-quest-vellum">
      <p>
        This story is real market history. We've hidden the company's name, the dates and the price
        level. You'll find out who it was at the end.
      </p>
      <button
        type="button"
        onClick={onDismiss}
        disabled={pending}
        className="mt-3 min-h-11 rounded-md border border-quest-gilt/70 bg-quest-lapis-deep px-5 font-quest-sans text-quest-vellum"
      >
        {pending ? 'Finding your quest…' : 'Got it'}
      </button>
    </section>
  );
}
