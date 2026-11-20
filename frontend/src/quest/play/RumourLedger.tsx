import Sheet from './Sheet';

export default function RumourLedger({ rumours, onClose }: { rumours: readonly string[]; onClose: () => void }): React.JSX.Element {
  return (
    <Sheet title="Rumour ledger" subtitle="Every rumour heard so far" onClose={onClose}>
      {rumours.length === 0 ? (
        <p className="font-quest text-base">No rumours heard yet.</p>
      ) : (
        <ul className="list-disc space-y-2 pl-5 font-quest text-base leading-snug">
          {rumours.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
