import { useSyncExternalStore } from 'react';

const STORAGE_KEY = 'fq.quest.v1';
const DEFAULT_PATH = '/quest';

type QuestStatus = 'in_progress' | 'finished';

interface QuestRecord {
  v: 1;
  status: QuestStatus;
  lastPath: string;
  savedAt: number;
  state: unknown;
}

export interface QuestMeta {
  inProgress: boolean;
  resumePath: string;
}

let memoryRecord: QuestRecord | null = null;
let storageFailed = false;
const listeners = new Set<() => void>();

const noQuest: QuestMeta = { inProgress: false, resumePath: DEFAULT_PATH };
let snapshot: QuestMeta = noQuest;

function isRecord(value: unknown): value is QuestRecord {
  if (typeof value !== 'object' || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    r.v === 1 &&
    (r.status === 'in_progress' || r.status === 'finished') &&
    typeof r.lastPath === 'string' &&
    typeof r.savedAt === 'number' &&
    'state' in r
  );
}

function removeKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable; nothing to remove
  }
}

function readRecord(): QuestRecord | null {
  if (storageFailed) return memoryRecord;
  let raw: string | null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    storageFailed = true;
    return memoryRecord;
  }
  if (raw === null) return memoryRecord;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (isRecord(parsed)) return parsed;
  } catch {
    // corrupt JSON falls through to discard
  }
  removeKey();
  memoryRecord = null;
  return null;
}

function writeRecord(record: QuestRecord | null): void {
  memoryRecord = record;
  try {
    if (record) localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
    else localStorage.removeItem(STORAGE_KEY);
    storageFailed = false;
  } catch {
    storageFailed = true;
  }
  refreshSnapshot();
  listeners.forEach((l) => l());
}

function toMeta(record: QuestRecord | null): QuestMeta {
  return record && record.status === 'in_progress'
    ? { inProgress: true, resumePath: record.lastPath }
    : noQuest;
}

function refreshSnapshot(): void {
  const next = toMeta(readRecord());
  if (next.inProgress !== snapshot.inProgress || next.resumePath !== snapshot.resumePath) {
    snapshot = next;
  }
}

export function getQuestMeta(): QuestMeta {
  refreshSnapshot();
  return snapshot;
}

export function startQuest(): void {
  writeRecord({ v: 1, status: 'in_progress', lastPath: DEFAULT_PATH, savedAt: Date.now(), state: null });
}

export function saveProgress(path: string, state: unknown): void {
  writeRecord({ v: 1, status: 'in_progress', lastPath: path, savedAt: Date.now(), state });
}

export function finishQuest(): void {
  const current = readRecord();
  writeRecord({
    v: 1,
    status: 'finished',
    lastPath: current?.lastPath ?? DEFAULT_PATH,
    savedAt: Date.now(),
    state: current?.state ?? null,
  });
}

export function clearQuest(): void {
  writeRecord(null);
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useQuestMeta(): QuestMeta {
  return useSyncExternalStore(subscribe, getQuestMeta, getQuestMeta);
}
