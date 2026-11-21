import { useState } from 'react';
import './BuddyMascot.css';
import EduBubbles from './EduBubbles';
import { waitingLabel } from './useEdu';
import type { EduMoment } from '../../api/types';

const frames = Object.entries(import.meta.glob<string>(
  '../../assets/commerzbuddy-frames-gif/frame_*.png',
  { eager: true, import: 'default' },
)).sort(([a], [b]) => a.localeCompare(b)).map(([, url]) => url);

interface BuddyMascotProps {
  onOpenChat: () => void;
  /** Learning moments waiting: Buddy wakes up and one bubble shows per moment (max 3). */
  pending?: EduMoment[];
  poppedId?: string | null;
}

export default function BuddyMascot({ onOpenChat, pending = [], poppedId = null }: BuddyMascotProps) {
  const [playing, setPlaying] = useState(false);
  const waiting = Math.min(pending.length, 3);
  return (
    <div className="buddy-wrap">
    <EduBubbles ids={pending.slice(0, 3).map((m) => m.id)} poppedId={poppedId} />
    <button
      type="button"
      aria-label={waiting > 0 ? `Chat with CommerzBuddy, ${waitingLabel(waiting)}` : 'Chat with CommerzBuddy'}
      data-awake={waiting > 0}
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
    </div>
  );
}
