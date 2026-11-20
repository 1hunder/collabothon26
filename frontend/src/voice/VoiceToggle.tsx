import { Volume2, VolumeX } from 'lucide-react';
import { useVoice } from './context';

export default function VoiceToggle(): React.JSX.Element {
  const { enabled, toggle } = useVoice();
  const Icon = enabled ? Volume2 : VolumeX;
  return (
    <button
      type="button"
      aria-label={enabled ? 'Voice on' : 'Voice off'}
      aria-pressed={enabled}
      onClick={toggle}
      className="flex h-11 w-11 items-center justify-center rounded-full text-quest-vellum"
    >
      <Icon aria-hidden="true" size={22} />
    </button>
  );
}
