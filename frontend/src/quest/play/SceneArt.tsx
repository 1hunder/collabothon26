import { useState } from 'react';
import type { PlayLocation } from '../../api/types';
import { artSrc } from './artSrc';

interface SceneArtProps {
  location: PlayLocation | undefined;
}

/** Plain dark backdrop with the location name; the picture crossfades in once it has decoded. */
export default function SceneArt({ location }: SceneArtProps): React.JSX.Element {
  const src = artSrc(location);
  return (
    <div aria-hidden="true" className="absolute inset-0 overflow-hidden bg-gradient-to-b from-[#1d2547] via-[#191630] to-[#120f1a]">
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5">
        <span className="font-quest-title text-[40px] text-quest-vellum/30">{location?.name ?? ''}</span>
      </div>
      {src !== null ? <FadeImage key={src} src={src} /> : null}
      <div className="absolute inset-0 bg-[radial-gradient(90%_60%_at_50%_35%,transparent_40%,rgba(10,8,16,0.55)_100%),linear-gradient(to_bottom,rgba(10,8,16,0.35),transparent_22%,transparent_55%,rgba(10,8,16,0.85))]" />
    </div>
  );
}

function FadeImage({ src }: { src: string }): React.JSX.Element | null {
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
  if (state === 'failed') return null;
  return (
    <img
      src={src}
      alt=""
      data-testid="scene-art"
      onLoad={() => setState('ready')}
      onError={() => setState('failed')}
      className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 motion-reduce:transition-none ${
        state === 'ready' ? 'opacity-100' : 'opacity-0'
      }`}
    />
  );
}
