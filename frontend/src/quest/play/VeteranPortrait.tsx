import { useId } from 'react';
import type { VeteranMood } from '../../api/veteran';

/**
 * Brannoc Greyhallow, the Veteran: hooded ranger, one eye under a patch, grey beard, clay pipe,
 * and his old bone d20 on a cord. Pure SVG like BuddyToken; the mood only moves the brows, the eye
 * and the mouth. The pipe ember and smoke are the idle animation (off under reduced motion).
 */

const SKIN_LINE = '#8A5E45';
const BROW = '#9C978D';

function brow(x: number, y: number, side: -1 | 1, mood: VeteranMood): string {
  switch (mood) {
    case 'pondering':
      return side < 0 ? `M${x - 8} ${y - 14} Q${x} ${y - 19} ${x + 8} ${y - 13}` : `M${x - 8} ${y - 9} L${x + 8} ${y - 10}`;
    case 'approving':
      return `M${x - 8} ${y - 11} Q${x} ${y - 16} ${x + 8} ${y - 11}`;
    case 'stern':
      return side < 0 ? `M${x - 8} ${y - 13} L${x + 7} ${y - 7}` : `M${x - 7} ${y - 7} L${x + 8} ${y - 13}`;
    default:
      return `M${x - 8} ${y - 10} Q${x} ${y - 14} ${x + 8} ${y - 10}`;
  }
}

function mouth(x: number, y: number, mood: VeteranMood): string {
  switch (mood) {
    case 'approving':
      return `M${x - 7} ${y - 1} Q${x} ${y + 5} ${x + 7} ${y - 1}`;
    case 'stern':
      return `M${x - 7} ${y + 2} Q${x} ${y - 3} ${x + 7} ${y + 2}`;
    case 'pondering':
      return `M${x - 6} ${y + 1} Q${x + 1} ${y - 1} ${x + 6} ${y + 2}`;
    default:
      return `M${x - 6} ${y} Q${x} ${y + 1} ${x + 6} ${y}`;
  }
}

/** A flat d20: hexagon outline, the centre face, the edges to the rim. */
export function D20Glyph({ cx, cy, size, fill, face, stroke, strokeWidth = 3, num }: {
  cx: number;
  cy: number;
  size: number;
  fill: string;
  face?: string;
  stroke: string;
  strokeWidth?: number;
  num?: number;
}): React.JSX.Element {
  const k = size / 100;
  const P = (x: number, y: number): string => `${(cx + (x - 50) * k).toFixed(1)},${(cy + (y - 50) * k).toFixed(1)}`;
  const hex: [number, number][] = [[50, 4], [90, 27], [90, 73], [50, 96], [10, 73], [10, 27]];
  const tri: [number, number][] = [[50, 26], [74, 64], [26, 64]];
  const edges: [number, number][] = [[0, 0], [0, 1], [0, 5], [1, 1], [1, 2], [1, 3], [2, 3], [2, 4], [2, 5]];
  const sw = strokeWidth * k;
  const lines = edges.map(([t, h]) => `M${P(...tri[t]!)}L${P(...hex[h]!)}`).join('');
  return (
    <g>
      <polygon points={hex.map((p) => P(...p)).join(' ')} fill={fill} stroke={stroke} strokeWidth={sw} strokeLinejoin="round" />
      <polygon points={tri.map((p) => P(...p)).join(' ')} fill={face ?? fill} stroke={stroke} strokeWidth={sw} strokeLinejoin="round" />
      <path d={lines} stroke={stroke} strokeWidth={sw} fill="none" />
      {num !== undefined ? (
        <text
          x={cx}
          y={cy + 4.5 * k}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="Alegreya, serif"
          fontWeight={700}
          fontSize={24 * k}
          fill="#3A2E1C"
        >
          {num}
        </text>
      ) : null}
    </g>
  );
}

const glow: Record<VeteranMood, string> = {
  listening: 'drop-shadow-[0_0_14px_rgba(111,181,168,0.45)]',
  pondering: 'drop-shadow-[0_0_14px_rgba(232,220,194,0.4)]',
  approving: 'drop-shadow-[0_0_16px_rgba(201,162,39,0.6)]',
  stern: 'drop-shadow-[0_0_16px_rgba(226,128,122,0.6)]',
};

interface VeteranPortraitProps {
  mood?: VeteranMood;
  /** bust: the whole figure (200×240); token: the face in a coin (square). */
  variant?: 'bust' | 'token';
  /** Without the warm backdrop: the figure stands straight on the scene art. */
  bare?: boolean;
  className?: string;
  /** Glow around the figure, coloured by mood. */
  glowing?: boolean;
  title?: string;
}

export default function VeteranPortrait({
  mood = 'listening',
  variant = 'bust',
  bare = false,
  className = '',
  glowing = false,
  title,
}: VeteranPortraitProps): React.JSX.Element {
  const uid = useId().replace(/:/g, '');
  const viewBox = variant === 'token' ? '48 52 104 104' : '0 0 200 240';
  return (
    <svg
      viewBox={viewBox}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      data-mood={mood}
      className={`${glowing ? glow[mood] : ''} ${className}`}
      xmlns="http://www.w3.org/2000/svg"
    >
      {bare ? null : (
        <>
          <defs>
            <radialGradient id={`${uid}bg`} cx="50%" cy="42%" r="65%">
              <stop offset="0" stopColor="#4A3020" />
              <stop offset="1" stopColor="#161F3D" />
            </radialGradient>
          </defs>
          <rect width="200" height="240" fill={`url(#${uid}bg)`} />
        </>
      )}
      {/* cloak, hood, face */}
      <path d="M18 240 C22 192 52 170 100 166 C148 170 178 192 182 240Z" fill="#4A3826" />
      <path d="M44 198 C40 120 58 52 100 40 C142 52 160 120 156 198 C146 172 134 160 100 158 C66 160 54 172 44 198Z" fill="#2F3D35" />
      <ellipse cx="100" cy="112" rx="30" ry="37" fill="#C3916B" />
      <path d="M70 102 C72 76 86 66 100 66 C114 66 128 76 130 102 C122 86 112 82 100 82 C88 82 78 86 70 102Z" fill="#000" opacity=".28" />
      <path d="M63 152 C58 102 70 62 100 57 C130 62 142 102 137 152" fill="none" stroke="#3E5045" strokeWidth="10" strokeLinecap="round" />
      {/* the scar, the open eye, the patch */}
      <path d="M84 88 L94 121" stroke="#8E5B45" strokeWidth="2.5" strokeLinecap="round" />
      {mood === 'approving' ? (
        <path d="M84 105 Q88 101 92 105" stroke="#15121A" strokeWidth="2.2" strokeLinecap="round" fill="none" />
      ) : (
        <ellipse cx="88" cy="104" rx="3" ry={mood === 'stern' ? 1.8 : 3.2} fill="#15121A" />
      )}
      <path data-part="brow" d={brow(88, 104, -1, mood)} stroke={BROW} strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d={brow(112, 104, 1, mood)} stroke={BROW} strokeWidth="4" strokeLinecap="round" fill="none" />
      <path d="M71 87 Q90 92 105 100 M120 106 L131 109" stroke="#15121A" strokeWidth="2.4" fill="none" />
      <ellipse cx="112" cy="104" rx="9" ry="7.5" fill="#1D1A22" />
      <path d="M99 106 Q95 118 98 121 Q101 123 104 120" fill="none" stroke={SKIN_LINE} strokeWidth="2" />
      {/* beard, mouth, moustache */}
      <path d="M71 116 C70 152 84 178 100 184 C116 178 130 152 129 116 C122 134 112 140 100 140 C88 140 78 134 71 116Z" fill="#A9A49A" />
      <path d="M86 152 q2 10 6 16 M100 156 v18 M114 152 q-2 10 -6 16" stroke="#8D887F" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d={mouth(100, 136, mood)} stroke="#3A2A22" strokeWidth="2.2" strokeLinecap="round" fill="none" />
      <path d="M82 134 Q100 120 118 134 Q108 129 100 131 Q92 129 82 134Z" fill="#CFCAC0" />
      {/* the pipe */}
      <path d="M110 137 Q122 146 133 142" stroke="#5A3A22" strokeWidth="4" fill="none" strokeLinecap="round" />
      <path d="M129 128 h13 v11 q-6.5 5 -13 0Z" fill="#6B4428" />
      <ellipse cx="135.5" cy="129" rx="5" ry="2" fill="#F0A04B" className="animate-ember motion-reduce:animate-none" />
      <path
        d="M136 124 q-6 -7 0 -14 q6 -7 0 -14"
        stroke="#B9AE96"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
        style={{ transformBox: 'fill-box', transformOrigin: 'bottom' }}
        className="animate-smoke opacity-0 motion-reduce:hidden motion-reduce:animate-none"
      />
      {/* his old bone die on a cord */}
      <path d="M80 170 L100 196 L120 170" stroke="#2B2118" fill="none" strokeWidth="1.6" />
      <D20Glyph cx={100} cy={205} size={20} fill="#E6DCC6" stroke="#8A7B60" strokeWidth={4} />
    </svg>
  );
}

/** The Veteran's face in a gilt-rimmed coin, for chips and the topic picker. */
export function VeteranToken({ size = 28, mood = 'listening' }: { size?: number; mood?: VeteranMood }): React.JSX.Element {
  return (
    <span
      aria-hidden="true"
      style={{ width: size, height: size }}
      className="inline-block shrink-0 overflow-hidden rounded-full bg-quest-lapis shadow-[0_0_0_2px_#C9A227]"
    >
      <VeteranPortrait variant="token" mood={mood} className="block h-full w-full" />
    </span>
  );
}
