import bubbleUrl from '../../assets/edu-bubble.webp';
import './EduBubbles.css';

/**
 * One thought bubble with "!" above CommerzBuddy while any learning moment is waiting. Several
 * moments can be recorded; the count lives on the dock badge and in Buddy's offer, not here.
 */
export default function EduBubbles({ ids, poppedId }: { ids: string[]; poppedId: string | null }): React.JSX.Element | null {
  if (ids.length === 0) return null;
  const popped = poppedId !== null && ids.includes(poppedId);
  return (
    <span className="edu-bubbles" aria-hidden="true" data-testid="edu-bubbles">
      <img
        key={popped ? poppedId : 'bubble'}
        src={bubbleUrl}
        alt=""
        data-testid="edu-bubble"
        data-pop={popped}
        className="edu-bubble"
        draggable={false}
      />
    </span>
  );
}
