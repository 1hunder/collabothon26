import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { setCampaign } from '../quest/questStore';
import { ApiError, request } from './client';
import { postSse } from './sse';
import type {
  CampaignState,
  CommitDraft,
  CommitRequest,
  CreateCampaignRequest,
  CreateHeroRequest,
  DebriefData,
  FinishResult,
  Hero,
  LockResponse,
  OutcomeReveal,
  ScenarioSummary,
  XpResult,
} from './types';

export const queryKeys = {
  hero: ['hero'] as const,
  campaign: (id: string) => ['campaign', id] as const,
  playable: ['scenarios', 'playable'] as const,
};

/** GET /hero; a 404 means "no hero yet" and resolves to null. */
export async function fetchHero(): Promise<Hero | null> {
  try {
    return await request<Hero>('GET', '/hero');
  } catch (e: unknown) {
    if (e instanceof ApiError && e.kind === 'NotFound') return null;
    throw e;
  }
}

export function abandonCampaign(id: string): Promise<void> {
  return request('POST', `/campaigns/${id}/abandon`);
}

export function useHero() {
  return useQuery({ queryKey: queryKeys.hero, queryFn: fetchHero });
}

export function useCreateHero() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateHeroRequest) => request<Hero>('POST', '/hero', req),
    onSuccess: (hero) => qc.setQueryData(queryKeys.hero, hero),
  });
}

export function useChooseHeroClass() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (heroClass: CreateHeroRequest['class']) => request<Hero>('PATCH', '/hero', { class: heroClass }),
    onSuccess: (hero) => qc.setQueryData(queryKeys.hero, hero),
  });
}

export function useCampaign(id: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.campaign(id ?? ''),
    queryFn: () => request<CampaignState>('GET', `/campaigns/${id ?? ''}`),
    enabled: Boolean(id),
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateCampaignRequest) => request<CampaignState>('POST', '/campaigns', req),
    onSuccess: (campaign) => {
      setCampaign(campaign.id, campaign.scenario_id);
      qc.setQueryData(queryKeys.campaign(campaign.id), campaign);
    },
  });
}

export function usePlayableScenarios() {
  return useQuery({
    queryKey: queryKeys.playable,
    queryFn: () => request<ScenarioSummary[]>('GET', '/scenarios/playable'),
  });
}

// ---- Spec 003 slice 7: decision to finish ----

/** Patch the cached campaign (e.g. its phase) so route guards follow without a refetch race. */
export function patchCampaignCache(
  qc: ReturnType<typeof useQueryClient>,
  id: string,
  patch: Partial<CampaignState>,
): void {
  qc.setQueryData<CampaignState>(queryKeys.campaign(id), (c) => (c ? { ...c, ...patch } : c));
}

export function saveCommitDraft(id: string, draft: Partial<CommitDraft>): Promise<void> {
  return request<void>('PUT', `/campaigns/${id}/commit-draft`, draft);
}

/** Leave an open decision scene without trading; it comes back when the player asks to decide. */
export function leaveScene(id: string): Promise<{ market_scene: null }> {
  return request('POST', `/campaigns/${id}/scene/leave`);
}

export function resumePlay(id: string): Promise<{ phase: 'play'; commit_draft: CommitDraft | null }> {
  return request('POST', `/campaigns/${id}/resume-play`);
}

export function lockDecision(id: string, req: CommitRequest): Promise<LockResponse> {
  return request<LockResponse>('POST', `/campaigns/${id}/lock`, req);
}

/** "I'm ready to decide": seal the position as it stands, without the forecast form. */
export function quickLock(id: string): Promise<LockResponse> {
  return request<LockResponse>('POST', `/campaigns/${id}/lock`, { quick: true });
}

export function useOutcome(id: string) {
  return useQuery({
    queryKey: ['outcome', id] as const,
    queryFn: () => request<OutcomeReveal>('GET', `/campaigns/${id}/reveal`),
  });
}

/** POST /debrief (SSE); resolves with the final debrief from the `done` event. */
export async function streamDebrief(id: string): Promise<DebriefData> {
  let result: DebriefData | null = null;
  let failure: string | null = null;
  await postSse(`/campaigns/${id}/debrief`, {}, (ev) => {
    if (ev.event === 'done') result = ev.data as unknown as DebriefData;
    if (ev.event === 'error') failure = ev.data.message;
  });
  if (result === null) throw new Error(failure ?? 'Debrief unavailable');
  return result;
}

export function submitReflection(id: string, text: string): Promise<{ scenario_id: string }> {
  return request('POST', `/campaigns/${id}/reflection`, { text });
}

export function fetchXp(id: string): Promise<XpResult> {
  return request<XpResult>('POST', `/campaigns/${id}/xp`);
}

export function finishCampaign(id: string): Promise<FinishResult> {
  return request<FinishResult>('POST', `/campaigns/${id}/finish`);
}
