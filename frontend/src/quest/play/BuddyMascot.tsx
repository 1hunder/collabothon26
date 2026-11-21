import { useState } from 'react';
import './BuddyMascot.css';

const frames = Object.entries(import.meta.glob<string>(
  '../../assets/commerzbuddy-frames-gif/frame_*.png',
  { eager: true, import: 'default' },
)).sort(([a], [b]) => a.localeCompare(b)).map(([, url]) => url);

export default function BuddyMascot({ onArrive }: { onArrive: () => void }) {
  const [moving, setMoving] = useState(false);
  return (
    <div className="buddy-track">
      <button
        type="button"
        aria-label="Chat with CommerzBuddy"
        aria-disabled={moving}
        className="buddy-mascot"
        data-moving={moving}
        onClick={() => setMoving(true)}
        onAnimationEnd={event => {
          if (moving && event.target === event.currentTarget) onArrive();
        }}
      >
        <span className="buddy-frames" style={{
          animationTimingFunction: `steps(${frames.length}, jump-none)`,
          '--last-frame': `${(1 - frames.length) * 100}%`,
        } as React.CSSProperties}>
          {frames.map(url => <img key={url} src={url} alt="" draggable={false} />)}
        </span>
      </button>
    </div>
  );
}
