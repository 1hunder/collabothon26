export type ScenarioSource = 'gate' | 'reference_pack';

export interface ScenarioSummary {
  id: string;
  industry_shown: string;
  source: ScenarioSource;
}

export interface StoryBeat {
  story_day: number;
  headline: string;
  facts: string[];
}

export interface StoryPoint {
  story_day: number;
  price: number;
}

export interface CompanyCard {
  [field: string]: string | number;
}

/** Disguised view up to story today. Never contains dates. */
export interface ScenarioView {
  id: string;
  invented_name: string;
  industry_shown: string;
  beats: StoryBeat[];
  chart: StoryPoint[];
  company_card: CompanyCard;
}

export interface NewsPoint {
  story_day: number;
  real_date: string;
  real_price: number;
  headline: string;
}

export interface RealPoint {
  date: string;
  price: number;
}

export interface RevealData {
  real_name: string;
  ticker: string;
  start_date: string;
  end_date: string;
  series: RealPoint[];
  news_points: NewsPoint[];
  what_changed: string[];
  n_guessers: number;
}

export interface SessionResponse {
  session_id: string;
}

// ---- Spec 003: campaign engine (hand-written from tech §2.5) ----

export type HeroClass = 'guardian' | 'analyst' | 'investigator';

export type Interest = 'Gaming' | 'Fashion' | 'Sports' | 'Mobility' | 'Music' | 'Tech';

export type CampaignPhase =
  | 'setup'
  | 'play'
  | 'commit'
  | 'timeskip'
  | 'reveal'
  | 'debrief'
  | 'reflect'
  | 'company'
  | 'xp'
  | 'done';

export interface HeroItem {
  id: string;
  name: string;
  /** What the item does; shown on the hero screen. */
  description?: string;
}

export interface HeroHistoryEntry {
  campaign_id: string;
  interests: string[];
  total_xp: number;
  decision?: string;
  result_pct?: number | null;
  finished_at?: string;
}

export interface Hero {
  name: string;
  class: HeroClass;
  total_xp: number;
  items: HeroItem[];
  history: HeroHistoryEntry[];
  active_campaign_id: string | null;
}

export interface CreateHeroRequest {
  name: string;
  class: HeroClass;
}

export interface HeroResources {
  hp: number;
  hp_euros: number;
  focus: number;
  rerolls: number;
  keen_eye: number;
}

export type DecisionAction = 'invest' | 'dont_invest' | 'wait' | 'spread';
export type Confidence = 'low' | 'medium' | 'high';

/** The four commit answers. Amount only for invest/spread; all fields optional in a draft. */
export interface CommitDraft {
  action: DecisionAction | null;
  amount_eur: number | null;
  evidence: string;
  forecast_pct: number;
  confidence: Confidence | null;
}

export interface CommitRequest {
  action: DecisionAction;
  amount_eur?: number;
  evidence: string;
  forecast_pct: number;
  confidence: Confidence;
}

export interface LockResponse {
  locked_at: string;
  horizon_days: number;
}

export interface PortfolioBreakdown {
  starting_budget: number;
  cash_kept: number;
  invested: number;
  value_now: number;
  fees: number;
  final_value: number;
  pl_eur: number;
  pl_pct: number;
}

/** GET /campaigns/{id}/reveal: the anonymized outcome, every figure from the server. */
export interface OutcomeReveal {
  locked_at: string;
  horizon_days: number;
  /** Story-day series extended through the horizon. */
  series: StoryPoint[];
  decision_day: number;
  breakdown: PortfolioBreakdown;
  hp_before: number;
  hp_after: number;
  currency_note: string;
}

export interface WhatIfRow {
  key: 'dont_invest' | 'half' | 'all' | 'spread' | 'yours';
  label: string;
  final_value: number;
  pct: number;
  is_yours: boolean;
}

export interface DebriefData {
  sound_reasoning: string;
  overlooked: string;
  luck: string;
  forecast_line: string;
  reflection_question: string;
  whatif: WhatIfRow[];
}

export interface XpCategory {
  name: string;
  score: number;
  max: number;
  rationale: string;
  quote: string;
}

export interface XpResult {
  categories: XpCategory[];
  total: number;
}

export interface FinishResult {
  total_xp: number;
  new_item?: HeroItem | null;
}

export type ArtStatus = 'pending' | 'ready' | 'failed';

export interface PlayLocation {
  id: string;
  /** tavern | market_square | library for the fixed ones; a slug for campaign locations */
  key: string;
  name: string;
  description: string;
  fixed: boolean;
  art_status: ArtStatus;
  visited: boolean;
}

export interface BacklogEntry {
  seq: number;
  /** "You", "You (to Buddy)", "Campaign Master", "CommerzBuddy" or a character name */
  speaker: string;
  text: string;
}

export interface ClueEntry {
  clue_id: string;
  source: string;
  title: string;
  text: string;
}

/** Daily figures, already in story numbers and already cut at story today. */
export interface PriceRow {
  day: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface LibraryEntry {
  id: string;
  title: string;
  text: string;
}

export interface LibraryDocument {
  id: string;
  title: string;
  entries: LibraryEntry[];
}

export interface KeyFigure {
  id?: string;
  label: string;
  value: number | string;
  period?: string | null;
  explain?: string;
}

export interface CompanyCardState {
  name: string;
  trade: string;
  size: string;
  key_figures: KeyFigure[];
}

export interface ChallengeInfo {
  id: string;
  title: string;
  dc: number;
  state: string;
  optional: boolean;
  result: string | null;
  location: string | null;
}

export interface PendingRoll {
  type: 'roll';
  challenge_id: string;
  state: 'offered' | 'rolling';
}

export interface NewsInfo {
  headline: string;
  summary: string;
}

/** Resumable campaign state (GET /campaigns/{id}). Numbers are display values from the server. */
export interface CampaignState {
  id: string;
  scenario_id: string;
  phase: CampaignPhase;
  interests: string[];
  hero: { name: string; class: HeroClass; total_xp: number; items: string[] };
  hp: number;
  hp_eur: number;
  focus_left: number;
  rerolls_left: number;
  keen_eye_left: number;
  bonus_lead_available: boolean;
  turn_count: number;
  story_day: number;
  story_day_label: string;
  news_shown: boolean;
  news: NewsInfo | null;
  current_location_id: string | null;
  locations: PlayLocation[];
  backlog: BacklogEntry[];
  clues: ClueEntry[];
  library: { documents: LibraryDocument[]; company_card: CompanyCardState };
  price_board: PriceRow[];
  challenges: ChallengeInfo[];
  pending: PendingRoll | null;
  can_decide: boolean;
  opening_done: boolean;
  /** Suggestions of the latest Campaign Master reply, when the server keeps them for resuming. */
  suggestions?: string[];
  scenario?: { title: string; company_name: string; trade: string; horizon_label: string; budget_eur: number };
  // Fields used by the commit-to-finish screens (spec 003 slice 7).
  /** @deprecated the flat fields above are the source of truth (the backend sends no `resources`). */
  resources: HeroResources;
  budget_eur?: number;
  horizon_days?: number;
  offers_spread?: boolean;
  commit_draft?: CommitDraft | null;
  xp?: XpResult;
  debrief?: DebriefData;
}

export interface CreateCampaignRequest {
  interests: Interest[];
}

// ---- SSE events (tech §2.5) ----

export type DmEvent =
  | { event: 'status'; data: { state: string } }
  | { event: 'token'; data: { text: string } }
  | { event: 'card'; data: { kind: 'dice' | 'news'; [field: string]: unknown } }
  | { event: 'state'; data: { can_decide?: boolean; art_ready?: string[]; [field: string]: unknown } }
  | { event: 'done'; data: { text: string; audio_text_id?: string | null; [field: string]: unknown } }
  | { event: 'error'; data: { code: string; message: string } };

// ---- Play turn payloads ----

export type DiceMode = 'normal' | 'advantage';

/** The dice challenge offered to the player (SSE card or bonus-lead response). */
export interface DiceCard {
  kind: 'dice';
  roll_id: string;
  challenge_id: string;
  title: string;
  dc: number;
  bonus: number;
  keen_eye_available: boolean;
  keen_eye_left: number;
}

export interface NewsCard {
  kind: 'news';
  headline: string;
  summary: string;
  time_skip_label: string;
  story_day: number;
}

export interface RollResult {
  roll_id: string;
  challenge_id: string;
  title: string;
  dice: number[];
  used: number | null;
  bonus: number;
  total: number;
  dc: number;
  result: 'success' | 'setback';
  final: boolean;
  options: ('continue' | 'reroll' | 'accept')[];
  rerolled: boolean;
  rerolls_left: number;
  keen_eye_left: number;
  alt_source: string | null;
}

/** Extra fields of a `done` event for a Campaign Master turn. */
export interface TurnExtras {
  speaker?: string;
  suggestions?: string[];
  show_decide?: boolean;
  location?: { id: string; key: string; name: string };
  first_visit?: boolean;
  news_text?: string;
}

export interface JournalEntry {
  seq: number;
  type: string;
  [field: string]: unknown;
}
