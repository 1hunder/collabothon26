import { useSyncExternalStore } from 'react';

const STORAGE_KEY = 'fq.quest.v2';
const LEGACY_KEY = 'fq.quest.v1';
const DEFAULT_PATH = '/quest';

type QuestStatus = 'in_progress' | 'finished';

interface QuestRecord {
  v: 2;
  status: QuestStatus;
  lastPath: string;
  campaignId: string | null;
  scenarioId: string | null;
  disclosureSeen: boolean;
  savedAt: number;
}

export interface QuestMeta {
  inProgress: boolean;
  resumePath: string;
  campaignId: string | null;
  scenarioId: string | null;
  disclosureSeen: boolean;
}

let memoryRecord: QuestRecord | null = null;
let storageFailed = false;
const listeners = new Set<() => void>();

const noQuest: QuestMeta = {
  inProgress: false,
  resumePath: DEFAULT_PATH,
  campaignId: null,
  scenarioId: null,
  disclosureSeen: false,
};
let snapshot: QuestMeta = noQuest;

function isStatus(value: unknown): value is QuestStatus {
  return value === 'in_progress' || value === 'finished';
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isRecord(value: unknown): value is QuestRecord {
  if (typeof value !== 'object' || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    r.v === 2 &&
    isStatus(r.status) &&
    typeof r.lastPath === 'string' &&
    isNullableString(r.campaignId) &&
    isNullableString(r.scenarioId) &&
    typeof r.disclosureSeen === 'boolean' &&
    typeof r.savedAt === 'number'
  );
}

/** A v1 record keeps status and lastPath; the campaign is resolved later via GET /hero. */
function migrateV1(value: unknown): QuestRecord | null {
  if (typeof value !== 'object' || value === null) return null;
  const r = value as Record<string, unknown>;
  if (r.v !== 1 || !isStatus(r.status) || typeof r.lastPath !== 'string') return null;
  return {
    v: 2,
    status: r.status,
    lastPath: r.lastPath,
    campaignId: null,
    scenarioId: null,
    disclosureSeen: false,
    savedAt: typeof r.savedAt === 'number' ? r.savedAt : Date.now(),
  };
}

function removeKey(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // storage unavailable; nothing to remove
  }
}

function parse(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return undefined;
  }
}

function readRecord(): QuestRecord | null {
  if (storageFailed) return memoryRecord;
  let raw: string | null;
  let legacy: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) legacy = localStorage.getItem(LEGACY_KEY);
  } catch {
    storageFailed = true;
    return memoryRecord;
  }
  if (raw === null) {
    if (legacy === null) return memoryRecord;
    const migrated = migrateV1(parse(legacy));
    removeKey(LEGACY_KEY);
    if (migrated) {
      memoryRecord = migrated;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated));
      } catch {
        storageFailed = true;
      }
    }
    return migrated;
  }
  const parsed = parse(raw);
  if (isRecord(parsed)) return parsed;
  removeKey(STORAGE_KEY);
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
  if (!record) return noQuest;
  return {
    inProgress: record.status === 'in_progress',
    resumePath: record.status === 'in_progress' ? record.lastPath : DEFAULT_PATH,
    campaignId: record.campaignId,
    scenarioId: record.scenarioId,
    disclosureSeen: record.disclosureSeen,
  };
}

function sameMeta(a: QuestMeta, b: QuestMeta): boolean {
  return (
    a.inProgress === b.inProgress &&
    a.resumePath === b.resumePath &&
    a.campaignId === b.campaignId &&
    a.scenarioId === b.scenarioId &&
    a.disclosureSeen === b.disclosureSeen
  );
}

function refreshSnapshot(): void {
  const next = toMeta(readRecord());
  if (!sameMeta(next, snapshot)) snapshot = next;
}

function update(patch: Partial<Omit<QuestRecord, 'v' | 'savedAt'>>): void {
  const current = readRecord();
  writeRecord({
    v: 2,
    status: 'in_progress',
    lastPath: DEFAULT_PATH,
    campaignId: null,
    scenarioId: null,
    disclosureSeen: false,
    ...current,
    ...patch,
    savedAt: Date.now(),
  });
}

export function getQuestMeta(): QuestMeta {
  refreshSnapshot();
  return snapshot;
}

/** True once "Finish quest" has run; leaving the quest then needs no confirmation. */
export function isQuestFinished(): boolean {
  return readRecord()?.status === 'finished';
}

export function getScenarioId(): string | null {
  return getQuestMeta().scenarioId;
}

export function getDisclosureSeen(): boolean {
  return getQuestMeta().disclosureSeen;
}

export function startQuest(path = DEFAULT_PATH): void {
  writeRecord({
    v: 2,
    status: 'in_progress',
    lastPath: path,
    campaignId: null,
    scenarioId: null,
    disclosureSeen: false,
    savedAt: Date.now(),
  });
}

export function saveProgress(path: string): void {
  update({ status: 'in_progress', lastPath: path });
}

export function setCampaign(campaignId: string, scenarioId: string): void {
  update({ campaignId, scenarioId, disclosureSeen: false });
}

export function markDisclosureSeen(): void {
  update({ disclosureSeen: true });
}

export function finishQuest(): void {
  update({ status: 'finished' });
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
