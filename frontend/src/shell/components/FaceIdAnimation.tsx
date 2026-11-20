export type FaceIdPhase = 'scanning' | 'done';

// Pure presentation: inline SVG + CSS keyframes (see styles/index.css).
// Under prefers-reduced-motion the CSS shows static frames (scan icon, then check mark).
export default function FaceIdAnimation({ phase }: { phase: FaceIdPhase }): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 64 64"
      className="h-20 w-20 text-petrol"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={phase === 'done' ? 'Face ID successful' : 'Scanning face'}
      data-phase={phase}
    >
      <path d="M8 20V12a4 4 0 0 1 4-4h8M44 8h8a4 4 0 0 1 4 4v8M56 44v8a4 4 0 0 1-4 4h-8M20 56h-8a4 4 0 0 1-4-4v-8" />
      {phase === 'scanning' ? (
        <>
          <path d="M24 24v5M40 24v5M32 26v9h-3M24 42c4 4 12 4 16 0" />
          <line
            className="fid-scan-line stroke-brand-yellow"
            x1="12"
            y1="14"
            x2="52"
            y2="14"
            strokeWidth="3"
          />
        </>
      ) : (
        <path className="fid-check" d="M20 33l8 8 16-17" strokeWidth="4" />
      )}
    </svg>
  );
}
