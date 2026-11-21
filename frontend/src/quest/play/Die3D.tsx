import { useLayoutEffect, useRef } from 'react';
import {
  FACES,
  add,
  apply,
  axisAngle,
  cross,
  cssMatrix,
  dot,
  easeOutCubic,
  length,
  multiply,
  normalize,
  randomAxis,
  restingPose,
  rotation,
  scale,
  sub,
  transpose,
  type Mat3,
} from './d20';
import { prefersReducedMotion } from './useTypewriter';

/** Time the die takes to settle on the rolled face once the result is known. */
export const SETTLE_MS = 800;

const UNIT = 42; // px per geometry unit: the die is about 160 px across
const SIZE = 176;
const LIGHT = normalize([-0.35, -0.8, 0.5]); // from the upper left, toward the viewer
const SPIN_PER_MS = (4 * Math.PI) / 1000; // two turns a second while the server rolls

/** Each face as a CSS triangle placed in 3D. Computed once. */
const LAYOUT = FACES.map((f) => {
  const grow = 1.012; // slight overlap so no seams show between faces
  const at = (v: typeof f.a) => scale(add(f.cen, scale(sub(v, f.cen), grow)), UNIT);
  const top = at(f.a);
  let right = at(f.b);
  let left = at(f.c);
  const w = length(sub(right, left));
  const h = (w * Math.sqrt(3)) / 2;
  const basis = () => {
    const x = scale(sub(right, left), 1 / w);
    const origin = sub(top, scale(x, w / 2));
    return { x, y: scale(sub(left, origin), 1 / h), origin };
  };
  let b = basis();
  if (dot(cross(b.x, b.y), f.n) < 0) {
    [right, left] = [left, right];
    b = basis();
  }
  const { x, y, origin } = b;
  const transform = `matrix3d(${x[0]},${x[1]},${x[2]},0,${y[0]},${y[1]},${y[2]},0,${f.n[0]},${f.n[1]},${f.n[2]},0,${origin[0]},${origin[1]},${origin[2]},1)`;
  return { face: f, w, h, transform };
});

const resting = restingPose;

/**
 * A twenty-sided die in CSS 3D. With `value` null it spins; when a value arrives it settles,
 * turning from wherever it is onto that face. With reduced motion it shows the face at once.
 */
export default function Die3D({ value }: { value: number | null }): React.JSX.Element {
  const dieRef = useRef<HTMLDivElement>(null);
  const faceRefs = useRef<(HTMLDivElement | null)[]>([]);
  const fillRefs = useRef<(HTMLElement | null)[]>([]);
  const pose = useRef<Mat3>(resting(value ?? 20));

  useLayoutEffect(() => {
    const draw = (M: Mat3): void => {
      if (dieRef.current) dieRef.current.style.transform = cssMatrix(M);
      LAYOUT.forEach(({ face }, i) => {
        const light = Math.max(0, dot(apply(M, face.n), LIGHT));
        const l = 24 + 40 * light;
        const edge = faceRefs.current[i];
        const fill = fillRefs.current[i];
        if (edge) edge.style.background = `hsl(38 55% ${(l * 0.5).toFixed(1)}%)`;
        if (fill) fill.style.background = `linear-gradient(160deg, hsl(44 70% ${(l + 6).toFixed(1)}%), hsl(40 62% ${(l - 4).toFixed(1)}%))`;
      });
    };
    const still = prefersReducedMotion() || typeof window.requestAnimationFrame !== 'function';
    const target = value === null ? null : resting(value);
    if (still) {
      if (target) pose.current = target;
      draw(pose.current);
      return undefined;
    }

    const start = pose.current;
    const t0 = performance.now();
    let raf = 0;
    let frame: (now: number) => void;
    if (target === null) {
      const axis = randomAxis();
      frame = (now) => {
        pose.current = multiply(rotation(axis, (now - t0) * SPIN_PER_MS), start);
        draw(pose.current);
        raf = requestAnimationFrame(frame);
      };
    } else {
      // turn from the current pose onto the target, one extra full turn, easing out
      const { axis, angle } = axisAngle(multiply(start, transpose(target)));
      const turnAxis = axis ?? randomAxis();
      const total = angle + 2 * Math.PI;
      frame = (now) => {
        const p = Math.min(1, (now - t0) / SETTLE_MS);
        pose.current = p < 1 ? multiply(rotation(turnAxis, total * (1 - easeOutCubic(p))), target) : target;
        draw(pose.current);
        if (p < 1) raf = requestAnimationFrame(frame);
      };
    }
    draw(start);
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [value]);

  return (
    <div
      role="img"
      aria-label={value === null ? 'Twenty-sided die, rolling' : `Twenty-sided die showing ${value}`}
      className="relative"
      style={{ width: SIZE, height: SIZE + 14, perspective: '820px' }}
    >
      <div
        aria-hidden="true"
        className="absolute bottom-0 left-1/2 h-6 w-[140px] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(closest-side,rgba(0,0,0,0.6),rgba(0,0,0,0))]"
      />
      <div
        ref={dieRef}
        aria-hidden="true"
        style={{ position: 'absolute', left: '50%', top: SIZE / 2, width: 0, height: 0, transformStyle: 'preserve-3d', transformOrigin: '0 0' }}
      >
        {LAYOUT.map(({ face, w, h, transform }, i) => (
          <div
            key={face.num}
            ref={(el) => {
              faceRefs.current[i] = el;
            }}
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              width: w,
              height: h,
              transform,
              transformOrigin: '0 0',
              backfaceVisibility: 'hidden',
              WebkitBackfaceVisibility: 'hidden',
              clipPath: 'polygon(50% 0, 100% 100%, 0 100%)',
            }}
          >
            <i
              ref={(el) => {
                fillRefs.current[i] = el;
              }}
              style={{ position: 'absolute', inset: 0, clipPath: 'polygon(50% 7%, 94.5% 96%, 5.5% 96%)' }}
            />
            <b
              className={`absolute left-1/2 top-[66.6%] font-quest font-bold leading-none text-[#241806] ${face.num === 6 || face.num === 9 ? 'underline decoration-2 underline-offset-2' : ''}`}
              style={{ fontSize: Math.round(h * 0.42), transform: 'translate(-50%, -54%)', textShadow: '0 1px 0 rgba(255,236,180,0.45)' }}
            >
              {face.num}
            </b>
          </div>
        ))}
      </div>
    </div>
  );
}
