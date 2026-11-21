import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import type { QuestJob, Transaction } from './types';

export const personalKeys = {
  transactions: ['me', 'transactions'] as const,
  daily: ['quests', 'daily'] as const,
  quests: ['quests'] as const,
};

const POLL_MS = 4000;

export function isActive(job: QuestJob): boolean {
  return job.status === 'queued' || job.status === 'running';
}

export function useTransactions() {
  return useQuery({
    queryKey: personalKeys.transactions,
    queryFn: () => request<Transaction[]>('GET', '/me/transactions'),
    staleTime: Infinity,
  });
}

/**
 * Today's quest. POST /quests/daily is idempotent per day: on the first call after login it starts
 * generating (or, in demo mode, assigns the pre-created quest at once).
 */
export function useDailyQuest() {
  return useQuery({
    queryKey: personalKeys.daily,
    queryFn: () => request<QuestJob>('POST', '/quests/daily'),
    refetchInterval: (q) => (q.state.data && isActive(q.state.data) ? POLL_MS : false),
    retry: 1,
  });
}

/** Extra quests the player asked for (the daily one is shown separately). */
export function useExtraQuests() {
  return useQuery({
    queryKey: personalKeys.quests,
    queryFn: async () => (await request<QuestJob[]>('GET', '/quests')).filter((j) => j.kind === 'extra'),
    refetchInterval: (q) => (q.state.data?.some(isActive) ? POLL_MS : false),
  });
}

export function useGenerateQuest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => request<QuestJob>('POST', '/quests/generate'),
    onSuccess: (job) => {
      qc.setQueryData<QuestJob[]>(personalKeys.quests, (cur) => [job, ...(cur ?? [])]);
    },
  });
}
