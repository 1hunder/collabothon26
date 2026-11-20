import { baseUrl } from '../../api/client';
import type { PlayLocation } from '../../api/types';

/** Constant backgrounds ship with the app; campaign art comes from the API once it is ready. */
export function artSrc(location: PlayLocation | undefined): string | null {
  if (!location) return null;
  if (location.fixed) return `/backgrounds/${location.key.replace(/_/g, '-')}.webp`;
  return location.art_status === 'ready' ? `${baseUrl()}/locations/${location.id}/art` : null;
}
