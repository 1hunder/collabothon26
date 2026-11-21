export type BuddyMood = 'neutral' | 'thinking' | 'cautious' | 'cheering';

const glow: Record<BuddyMood, string> = {
  neutral: 'drop-shadow-[0_0_14px_rgba(111,181,168,0.55)]',
  thinking: 'drop-shadow-[0_0_14px_rgba(232,220,194,0.5)]',
  cautious: 'drop-shadow-[0_0_14px_rgba(201,162,39,0.6)]',
  cheering: 'drop-shadow-[0_0_16px_rgba(111,181,168,0.9)]',
};

interface BuddyTokenProps {
  size?: number;
  mood?: BuddyMood;
  className?: string;
}

/**
 * Placeholder token: a verdigris coin with a gilt rim and a simple glyph. The team's final art
 * (Lottie or sprite sheet) drops in behind this same component.
 */
export default function BuddyToken({ size = 76, mood = 'neutral', className = '' }: BuddyTokenProps): React.JSX.Element {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true" className={`${glow[mood]} ${className}`}>
      <circle cx="32" cy="32" r="30" fill="#C9A227" />
      <circle cx="32" cy="32" r="25" fill="#3E8A7E" />
      <circle cx="32" cy="32" r="21" fill="none" stroke="#6FB5A8" strokeWidth="1.5" />
      <path d="M32 18l3.5 9.5L45 31l-9.5 3.5L32 44l-3.5-9.5L19 31l9.5-3.5z" fill="#E8DCC2" />
    </svg>
  );
}
