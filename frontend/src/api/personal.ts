import { useQuery } from '@tanstack/react-query';
import { request } from './client';
import type { Transaction } from './types';

export const personalKeys = {
  transactions: ['me', 'transactions'] as const,
};

export function useTransactions() {
  return useQuery({
    queryKey: personalKeys.transactions,
    queryFn: () => request<Transaction[]>('GET', '/me/transactions'),
    staleTime: Infinity,
  });
}
