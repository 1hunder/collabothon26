import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { patchCampaignCache, streamDebrief } from '../../api/campaign';
import type { DebriefData } from '../../api/types';
import { useVoice } from '../../voice';
import WhatIfPanel from '../components/WhatIfPanel';
import ScreenBuddy from '../play/ScreenBuddy';
import { useActiveCampaign } from '../lib/useActiveCampaign';

/** `/quest/debrief`: three parts, the forecast line, What if…, then the reflection question. */
export default function Debrief(): React.JSX.Element {
  const { id, campaign } = useActiveCampaign();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const voice = useVoice();
  const [fetched, setFetched] = useState<DebriefData | null>(null);
  const [failed, setFailed] = useState(false);
  const debrief = campaign?.debrief ?? fetched;

  // Resume case: the phase is debrief but the text was never loaded.
  useEffect(() => {
    if (id === null || !campaign || campaign.debrief) return;
    let cancelled = false;
    streamDebrief(id)
      .then((d) => {
        if (!cancelled) setFetched(d);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, campaign]);

  const spoken = debrief?.sound_reasoning;
  useEffect(() => {
    if (spoken) voice.onPageShown(spoken, 'dm');
    // read once per debrief text
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spoken]);

  if (failed) return <p role="alert">Could not load the debrief. Please try again.</p>;
  if (!debrief || id === null) return <p role="status">The Campaign Master is writing…</p>;

  const parts: [string, string][] = [
    ['Sound reasoning', debrief.sound_reasoning],
    ...(debrief.how_you_reasoned ? ([['How you reasoned', debrief.how_you_reasoned]] as [string, string][]) : []),
    ['Overlooked', debrief.overlooked],
    ['Luck', debrief.luck],
  ];

  return (
    <div className="space-y-5 pb-8">
      <ScreenBuddy campaignId={id} screen="debrief" />
      <h1 className="font-quest-title text-4xl text-quest-gilt">Debrief</h1>
      {parts.map(([label, text]) => (
        <section key={label}>
          <h2 className="font-quest-title text-2xl text-quest-gilt">{label}</h2>
          <p>{text}</p>
        </section>
      ))}
      <p className="font-quest-sans italic text-quest-vellum-dim">{debrief.forecast_line}</p>
      <WhatIfPanel rows={debrief.whatif} />
      <p className="text-lg">{debrief.reflection_question}</p>
      <button
        type="button"
        onClick={() => {
          patchCampaignCache(qc, id, { phase: 'reflect' });
          void navigate('/quest/reflect', { replace: true });
        }}
        className="min-h-11 w-full rounded-md border border-quest-gilt/70 bg-quest-lapis-deep px-5 font-quest-sans text-lg font-bold"
      >
        Reflect
      </button>
    </div>
  );
}
