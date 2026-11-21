import { useState } from 'react';
import { useDmStream } from '../../api/useDmStream';
import { useVoice } from '../../voice';
import BuddyScene from './BuddyScene';
import BuddyToken from './BuddyToken';
import EduBubbles from './EduBubbles';
import { useEdu, waitingLabel } from './useEdu';
import type { EduMoment } from '../../api/types';

export type BuddyScreen = 'commit' | 'outcome' | 'debrief' | 'xp';

/**
 * CommerzBuddy on the non-play quest screens (commit, outcome, debrief, XP): a floating token
 * button that opens the same BuddyScene panel, telling the API which screen the question is from.
 */
export default function ScreenBuddy({ campaignId, screen }: { campaignId: string; screen: BuddyScreen }): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const edu = useEdu(campaignId);
  const stream = useDmStream(`/campaigns/${campaignId}/buddy`, (d) => edu.announce(d.extras.edu_new as EduMoment[] | undefined));
  const waiting = edu.pending.length;
  const voice = useVoice();
  return (
    <>
      {open ? (
        <div className="fixed inset-x-0 bottom-0 z-30 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-20">
          <BuddyScene
            stream={stream}
            edu={edu}
            screen={screen}
            onClose={() => {
              voice.stop();
              setOpen(false);
            }}
            onAsked={voice.stop}
            onPageShown={(text, kind, audioTextId) => voice.onPageShown(text, kind, audioTextId == null ? null : String(audioTextId))}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={waiting > 0 ? `Buddy, ${waitingLabel(waiting)}` : undefined}
          data-awake={waiting > 0}
          className="buddy-mascot-btn fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] right-4 z-30 flex min-h-11 items-center gap-1.5 rounded-full bg-quest-lapis px-3 font-quest-sans text-sm font-medium text-quest-verdigris-light shadow-lg"
        >
          <BuddyToken size={28} mood={waiting > 0 ? 'cheering' : 'neutral'} />
          <EduBubbles ids={edu.pending.map((m) => m.id)} poppedId={edu.poppedId} />
          Buddy
        </button>
      )}
    </>
  );
}
