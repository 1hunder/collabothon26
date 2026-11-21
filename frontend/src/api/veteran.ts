import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from './client';

/** The Veteran's speaker name (name tab) and his full name. */
export const VETERAN_NAME = 'Brannoc';
export const VETERAN_FULL_NAME = 'Brannoc Greyhallow';
export const VETERAN_TALK_PATH = '/hero/veteran/talk';
export const HABITS_TOPIC = 'habits';

export type VeteranMood = 'listening' | 'pondering' | 'approving' | 'stern';

export interface VeteranQuest {
  campaign_id: string;
  number: number;
  title: string;
  company: string;
  real_name: string | null;
  result: 'gain' | 'loss' | 'flat' | null;
  pnl_pct: number | null;
  forecast: string | null;
  tags: string[];
  xp: number;
  finished_at: string | null;
}

export interface ProfileTag {
  tag: string;
  label: string;
  count?: number;
}

export interface VeteranProfile {
  quests: number;
  gains: number;
  losses: number;
  xp: number;
  strengths: ProfileTag[];
  weaknesses: ProfileTag[];
  habits: ProfileTag[];
  emerging: ProfileTag[];
  milestones: { key: string; label: string; quest: number }[];
}

export interface VeteranMessage {
  id: string;
  role: 'player' | 'veteran';
  topic: string | null;
  text: string;
  mood: VeteranMood | null;
  suggestions: string[];
  show_timeline: boolean;
}

export interface VeteranLesson {
  id: number;
  text: string;
  campaign_id: string | null;
  quest_title: string | null;
  created_at: string;
}

export interface VeteranOverview {
  name: string;
  speaker: string;
  speaker_id: string;
  has_memory: boolean;
  /** A campaign is in progress: the Veteran never speaks of it. */
  running: boolean;
  /** Newest first. */
  quests: VeteranQuest[];
  profile: VeteranProfile | null;
  lessons: VeteranLesson[];
  messages: VeteranMessage[];
}

export type Judgement = 'sound' | 'hasty' | 'thin';
export type Luck = 'kind' | 'cruel' | 'neutral';

export interface TimelineDecision {
  seq: number;
  beat: string;
  when: string;
  day: string;
  action: 'buy' | 'sell' | 'hold';
  amount_eur: number;
  text: string;
  judgement: Judgement;
  luck: Luck;
  tags: string[];
}

export interface VeteranTimeline {
  campaign_id: string;
  number: number;
  title: string;
  company: string;
  real_name: string | null;
  decisions: TimelineDecision[];
  forecast: { pct: number | null; confidence: string | null; band: string; market: 'up' | 'down' | null };
  result: { kind: string | null; pnl_pct: number | null; pnl_eur: number | null; final_eur: number | null; budget_eur: number };
  missed: string[];
  xp: number;
  sound_overall: boolean;
}

/** Fields of the `done` event of POST /hero/veteran/talk. */
export interface VeteranDone {
  text: string;
  speaker: string;
  topic: string | null;
  mood: VeteranMood | null;
  suggestions: string[];
  show_timeline: boolean;
  degraded: boolean;
  audio_text_id: string;
}

export const veteranKeys = {
  overview: ['veteran'] as const,
  timeline: (cid: string) => ['veteran', 'timeline', cid] as const,
};

export function useVeteran(enabled = true) {
  return useQuery({
    queryKey: veteranKeys.overview,
    queryFn: () => request<VeteranOverview>('GET', '/hero/veteran'),
    enabled,
    staleTime: 0,
  });
}

export function useVeteranTimeline(cid: string | null) {
  return useQuery({
    queryKey: veteranKeys.timeline(cid ?? ''),
    queryFn: () => request<VeteranTimeline>('GET', `/hero/veteran/quests/${cid ?? ''}/timeline`),
    enabled: cid !== null,
  });
}

export function useAddLesson() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { text: string; campaign_id?: string | null }) =>
      request<VeteranLesson>('POST', '/hero/veteran/lessons', body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: veteranKeys.overview }),
  });
}

const RESULT_WORDS = { gain: 'gain', loss: 'loss', flat: 'even' } as const;

/** "Quest 2 · loss of 4.2%" style line for a remembered quest. */
export function questLine(q: Pick<VeteranQuest, 'number' | 'result' | 'pnl_pct'>): string {
  const word = q.result ? RESULT_WORDS[q.result] : null;
  const pct = q.pnl_pct !== null && q.result !== 'flat' ? ` ${q.pnl_pct > 0 ? '+' : ''}${q.pnl_pct}%` : '';
  return `Quest ${q.number}${word ? ` · ${word}${pct}` : ''}`;
}
