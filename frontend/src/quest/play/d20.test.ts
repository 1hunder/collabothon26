import { describe, expect, it } from 'vitest';
import { FACES, apply, axisAngle, faceFor, faceToViewer, multiply, rotation, transpose, type Mat3, type Vec3 } from './d20';

const close = (a: Vec3, b: Vec3): void => a.forEach((x, i) => expect(x).toBeCloseTo(b[i], 6));

describe('d20 geometry', () => {
  it('has twenty faces numbered 1 to 20, opposite faces adding up to 21', () => {
    expect(FACES).toHaveLength(20);
    expect([...FACES].map((f) => f.num).sort((a, b) => a - b)).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));
    for (const f of FACES) {
      const opposite = FACES.find((g) => g.n.every((x, i) => Math.abs(x + f.n[i]) < 1e-6));
      expect(opposite?.num).toBe(21 - f.num);
    }
  });

  it('turns every face toward the viewer with its number upright', () => {
    for (let n = 1; n <= 20; n++) {
      const f = faceFor(n);
      const M = faceToViewer(f);
      close(apply(M, f.n), [0, 0, 1]); // facing the viewer (+z)
      close(apply(M, f.up), [0, -1, 0]); // number's top toward screen-up (-y)
    }
  });

  it('recovers axis and angle, so the settle turn ends exactly on the target', () => {
    const target = faceToViewer(faceFor(17));
    const start: Mat3 = multiply(rotation([0.6, 0, 0.8], 2.2), faceToViewer(faceFor(3)));
    const { axis, angle } = axisAngle(multiply(start, transpose(target)));
    expect(axis).not.toBeNull();
    const back = multiply(rotation(axis as Vec3, angle + 2 * Math.PI), target);
    back.forEach((row, i) => close(row, start[i]));
  });
});
