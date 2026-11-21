import { useState } from 'react';
import './BuddyMascot.css';

const frames = Object.entries(import.meta.glob<string>(
  '../../assets/commerzbuddy-frames-gif/frame_*.png',
  { eager: true, import: 'default' },
)).sort(([a], [b]) => a.localeCompare(b)).map(([, url]) => url);

export default function BuddyMascot({ onOpenChat }: { onOpenChat: () => void }) {
  const [playing, setPlaying] = useState(false);
  return (
    <button
      type="button"
      aria-label="Chat with CommerzBuddy"
      aria-disabled={playing}
      className="buddy-mascot"
      data-playing={playing}
      onClick={() => setPlaying(true)}
    >
      <span className="buddy-frames" onAnimationEnd={onOpenChat} style={{
        animationTimingFunction: `steps(${frames.length}, jump-none)`,
        '--last-frame': `${(1 - frames.length) * 100}%`,
      } as React.CSSProperties}>
        {frames.map(url => <img key={url} src={url} alt="" draggable={false} />)}
      </span>
    </button>
  );
}
