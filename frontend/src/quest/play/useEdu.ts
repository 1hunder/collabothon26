import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { dismissMoment, MAX_EDU_BUBBLES } from '../../api/edu';
import { queryKeys, useCampaign } from '../../api/campaign';
import type { CampaignState, EduMoment } from '../../api/types';

export interface EduControls {
  campaignId: string;
  pending: EduMoment[];
  /** Id of the newest moment while its pop-in cue plays. */
  poppedId: string | null;
  /** A reply brought new moments (`edu_new`). */
  announce: (fresh: EduMoment[] | undefined) => void;
  /** A moment was viewed or dismissed: take it off the pending list. */
  settle: (id: string) => void;
  dismiss: (id: string) => Promise<void>;
}

/** Learning moments waiting for this campaign, read from the campaign state the API sends. */
export function useEdu(campaignId: string): EduControls {
  const qc = useQueryClient();
  const campaign = useCampaign(campaignId);
  const [poppedId, setPoppedId] = useState<string | null>(null);
  const pending = (campaign.data?.edu?.pending ?? []).slice(0, MAX_EDU_BUBBLES);

  const write = useCallback(
    (fn: (list: EduMoment[]) => EduMoment[]): void => {
      qc.setQueryData<CampaignState>(queryKeys.campaign(campaignId), (c) => {
        if (!c) return c;
        const next = fn(c.edu?.pending ?? []).slice(0, MAX_EDU_BUBBLES);
        return { ...c, edu: { pending: next, pending_count: next.length } };
      });
    },
    [qc, campaignId],
  );
  const announce = useCallback(
    (fresh: EduMoment[] | undefined): void => {
      if (!fresh || fresh.length === 0) return;
      write((list) => [...list, ...fresh.filter((m) => !list.some((p) => p.id === m.id))]);
      setPoppedId(fresh[fresh.length - 1]?.id ?? null);
    },
    [write],
  );
  const settle = useCallback((id: string): void => write((list) => list.filter((m) => m.id !== id)), [write]);
  const dismiss = useCallback(
    async (id: string): Promise<void> => {
      settle(id);
      try {
        await dismissMoment(campaignId, id);
      } catch {
        void qc.invalidateQueries({ queryKey: queryKeys.campaign(campaignId) });
      }
    },
    [settle, qc, campaignId],
  );
  return { campaignId, pending, poppedId, announce, settle, dismiss };
}

export function waitingLabel(count: number): string {
  return `${count} learning ${count === 1 ? 'moment' : 'moments'} waiting`;
}
