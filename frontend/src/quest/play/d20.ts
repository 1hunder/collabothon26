/**
 * Geometry for the 3D twenty-sided die: a regular icosahedron with numbered faces (opposite faces
 * add up to 21) and the 3x3 rotation helpers the CSS renderer needs. Pure, no DOM.
 *
 * Space is CSS space: x right, y down, z toward the viewer.
 */

export type Vec3 = [number, number, number];
/** 3x3 rotation as three rows. */
export type Mat3 = [Vec3, Vec3, Vec3];

export interface D20Face {
  /** Corners, counter-clockwise seen from outside; `a` is the corner above the number. */
  a: Vec3;
  b: Vec3;
  c: Vec3;
  /** Outward unit normal. */
  n: Vec3;
  cen: Vec3;
  /** Unit vector in the face plane from the centre toward `a` (the number's "up"). */
  up: Vec3;
  num: number;
}

export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const length = (a: Vec3): number => Math.hypot(a[0], a[1], a[2]);
export const normalize = (a: Vec3): Vec3 => scale(a, 1 / length(a));

const PHI = (1 + Math.sqrt(5)) / 2;
const VERTS: Vec3[] = [
  [-1, PHI, 0], [1, PHI, 0], [-1, -PHI, 0], [1, -PHI, 0],
  [0, -1, PHI], [0, 1, PHI], [0, -1, -PHI], [0, 1, -PHI],
  [PHI, 0, -1], [PHI, 0, 1], [-PHI, 0, -1], [-PHI, 0, 1],
]; // every edge has length 2

/** Distance from the centre to a corner, for the vertices above. */
export const CIRCUMRADIUS = length(VERTS[0]);

function buildFaces(): D20Face[] {
  const isEdge = (p: number, q: number): boolean => Math.abs(length(sub(VERTS[p], VERTS[q])) - 2) < 1e-6;
  const faces: D20Face[] = [];
  for (let i = 0; i < 12; i++)
    for (let j = i + 1; j < 12; j++)
      for (let k = j + 1; k < 12; k++) {
        if (!(isEdge(i, j) && isEdge(j, k) && isEdge(i, k))) continue;
        const a = VERTS[i];
        let b = VERTS[j];
        let c = VERTS[k];
        const cen = scale(add(add(a, b), c), 1 / 3);
        let n = normalize(cross(sub(b, a), sub(c, a)));
        if (dot(n, cen) < 0) {
          [b, c] = [c, b];
          n = scale(n, -1);
        }
        faces.push({ a, b, c, n, cen, up: normalize(sub(a, cen)), num: 0 });
      }
  let next = 1;
  for (const f of faces) {
    if (f.num) continue;
    const opposite = faces.find((g) => dot(g.n, f.n) < -0.999);
    if (!opposite) throw new Error('icosahedron face without an opposite');
    f.num = next;
    opposite.num = 21 - next;
    next += 1;
  }
  return faces;
}

export const FACES: readonly D20Face[] = buildFaces();

export function faceFor(num: number): D20Face {
  const f = FACES.find((x) => x.num === num);
  if (!f) throw new Error(`no d20 face ${num}`);
  return f;
}

export const IDENTITY: Mat3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

export function multiply(A: Mat3, B: Mat3): Mat3 {
  const row = (r: Vec3): Vec3 => [
    r[0] * B[0][0] + r[1] * B[1][0] + r[2] * B[2][0],
    r[0] * B[0][1] + r[1] * B[1][1] + r[2] * B[2][1],
    r[0] * B[0][2] + r[1] * B[1][2] + r[2] * B[2][2],
  ];
  return [row(A[0]), row(A[1]), row(A[2])];
}

export const apply = (M: Mat3, v: Vec3): Vec3 => [dot(M[0], v), dot(M[1], v), dot(M[2], v)];

export const transpose = (M: Mat3): Mat3 => [
  [M[0][0], M[1][0], M[2][0]],
  [M[0][1], M[1][1], M[2][1]],
  [M[0][2], M[1][2], M[2][2]],
];

/** Rotation by `angle` radians about the unit `axis`. */
export function rotation(axis: Vec3, angle: number): Mat3 {
  const [x, y, z] = axis;
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const k = 1 - c;
  return [
    [c + x * x * k, x * y * k - z * s, x * z * k + y * s],
    [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
    [z * x * k - y * s, z * y * k + x * s, c + z * z * k],
  ];
}

/** Axis and angle of a rotation matrix; the axis is undefined (null) for a near-zero angle. */
export function axisAngle(M: Mat3): { axis: Vec3 | null; angle: number } {
  const angle = Math.acos(Math.min(1, Math.max(-1, (M[0][0] + M[1][1] + M[2][2] - 1) / 2)));
  if (angle < 1e-4) return { axis: null, angle: 0 };
  if (Math.PI - angle < 1e-4) {
    // 180 degrees: the axis is the column of (M + I) with the largest diagonal entry
    const i = [0, 1, 2].reduce((best, j) => (M[j][j] > M[best][best] ? j : best), 0);
    const col: Vec3 = [M[0][i] + (i === 0 ? 1 : 0), M[1][i] + (i === 1 ? 1 : 0), M[2][i] + (i === 2 ? 1 : 0)];
    return { axis: normalize(col), angle };
  }
  const axis = normalize([M[2][1] - M[1][2], M[0][2] - M[2][0], M[1][0] - M[0][1]]);
  return { axis, angle };
}

/** The orientation that turns `face` toward the viewer with its number upright. */
export function faceToViewer(face: D20Face): Mat3 {
  const r3 = face.n;
  const r2 = scale(face.up, -1);
  return [cross(r2, r3), r2, r3];
}

/**
 * A small tilt on the resting pose so the die reads as 3D. Kept small so the rolled face stays
 * in the centre of the die: a bigger tilt moves it off to the side.
 */
export const REST_TILT: Mat3 = multiply(rotation([0, 1, 0], 0.1), rotation([1, 0, 0], 0.13));

/** Where the die rests when it shows `value`: that face toward the viewer, centred and upright. */
export const restingPose = (value: number): Mat3 => multiply(REST_TILT, faceToViewer(faceFor(value)));

/** CSS `matrix3d` (column-major) for a rotation, optionally with a translation in px. */
export function cssMatrix(M: Mat3, t: Vec3 = [0, 0, 0]): string {
  return `matrix3d(${M[0][0]},${M[1][0]},${M[2][0]},0,${M[0][1]},${M[1][1]},${M[2][1]},0,${M[0][2]},${M[1][2]},${M[2][2]},0,${t[0]},${t[1]},${t[2]},1)`;
}

export function randomAxis(rand: () => number = Math.random): Vec3 {
  for (;;) {
    const v: Vec3 = [rand() - 0.5, rand() - 0.5, rand() - 0.5];
    if (length(v) > 0.05) return normalize(v);
  }
}

export const easeOutCubic = (p: number): number => 1 - Math.pow(1 - p, 3);
