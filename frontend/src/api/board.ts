import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import type { QuestBoard, QuestCard, QuestCardDetail } from './types';

export const boardKeys = {
  board: ['quests', 'board'] as const,
  detail: (id: string) => ['quests', 'board', id] as const,
};

export const BOARD_POLL_MS = 4000;

export function isGenerating(card: QuestCard): boolean {
  return card.status === 'generating';
}

/** The board; polled every few seconds while any notice is still being written. */
export function useBoard() {
  return useQuery({
    queryKey: boardKeys.board,
    queryFn: () => request<QuestBoard>('GET', '/quests/board'),
    refetchInterval: (q) =>
      q.state.data && [...q.state.data.curated, ...q.state.data.mine].some(isGenerating) ? BOARD_POLL_MS : false,
  });
}

export function useBoardQuest(id: string | null) {
  return useQuery({
    queryKey: boardKeys.detail(id ?? ''),
    queryFn: () => request<QuestCardDetail>('GET', `/quests/board/${id ?? ''}`),
    enabled: id !== null,
  });
}

/** POST /quests/generate: commission a quest, from a theme or from the player's own spending. */
export function useCommissionQuest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (theme?: string) =>
      request<QuestCard>('POST', '/quests/generate', theme ? { theme } : {}),
    onSuccess: (card) => {
      qc.setQueryData<QuestBoard>(boardKeys.board, (b) =>
        b ? { ...b, mine: [card, ...b.mine.filter((c) => c.id !== card.id)] } : b,
      );
      void qc.invalidateQueries({ queryKey: boardKeys.board });
    },
  });
}
