export const NAME_MIN = 2;
export const NAME_MAX = 20;
const namePattern = /^[\p{L}\p{N} '-]+$/u;

export type NameError = 'length' | 'characters' | null;

/** Trimmed 2-20 characters; letters, numbers, spaces, hyphens and apostrophes only. */
export function validateName(raw: string): NameError {
  const name = raw.trim();
  if (name.length < NAME_MIN || name.length > NAME_MAX) return 'length';
  return namePattern.test(name) ? null : 'characters';
}
