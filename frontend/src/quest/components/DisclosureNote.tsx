interface DisclosureNoteProps {
  onDismiss: () => void;
}

export default function DisclosureNote({ onDismiss }: DisclosureNoteProps): React.JSX.Element {
  return (
    <section className="rounded-lg border border-quest-gilt bg-quest-lapis p-4 font-quest text-quest-vellum">
      <p>
        This story is real market history. We've hidden the company's name, the dates and the price
        level. You'll find out who it was at the end.
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className="mt-3 min-h-11 rounded-md bg-quest-verdigris px-5 font-quest-sans text-quest-vellum"
      >
        Got it
      </button>
    </section>
  );
}
