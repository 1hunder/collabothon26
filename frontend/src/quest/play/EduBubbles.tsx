import './EduBubbles.css';

/** Up to three "!" speech bubbles stacked above CommerzBuddy, one per waiting learning moment. */
export default function EduBubbles({ ids, poppedId }: { ids: string[]; poppedId: string | null }): React.JSX.Element | null {
  if (ids.length === 0) return null;
  return (
    <span className="edu-bubbles" aria-hidden="true" data-testid="edu-bubbles">
      {ids.map((id, i) => (
        <span key={id} data-testid="edu-bubble" data-pop={id === poppedId} className="edu-bubble" style={{ '--i': i } as React.CSSProperties}>
          !
        </span>
      ))}
    </span>
  );
}
