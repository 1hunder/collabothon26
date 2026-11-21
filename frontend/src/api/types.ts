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

/** Prices are numbers in the app; the 002 endpoints send decimal strings, coerced in api/client.ts. */
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
  key?: string;
  name: string;
  /** What the item does; shown on the hero screen. */
  description?: string;
}

export interface HeroHistoryEntry {
  campaign_id: string;
  interests: string[];
  total_xp: number;
  decision?: string | null;
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

export type DecisionAction = 'invest' | 'dont_invest' | 'wait' | 'spread';
export type Confidence = 'low' | 'medium' | 'high';

/** The four commit answers. Amount only for invest/spread; all fields optional in a draft. */
/** The seal: what the player did with their coins comes from the decisions they wrote during the
 * campaign; the seal adds the forecast, the confidence and an optional closing note. */
export interface CommitDraft {
  evidence: string;
  forecast_pct: number;
  confidence: Confidence | null;
}

export interface CommitRequest {
  evidence?: string;
  forecast_pct: number;
  confidence: Confidence;
}

// ---- decisions throughout the campaign ----

/** The hero's coins at today's board price. Euros only (engine computed). */
export interface Purse {
  cash_eur: number;
  position_eur: number;
  total_eur: number;
}

export type DecisionBeat = 'opening' | 'news' | 'decision' | 'story';
export type TradeAction = 'buy' | 'sell' | 'hold';

/** A decision scene the story has put in front of the hero; their next written action answers it. */
export interface MarketScene {
  beat: DecisionBeat;
  story_day: number;
  text: string | null;
  suggestions: string[];
}

export interface MarketCard {
  kind: 'market';
  beat: DecisionBeat;
  text: string;
  suggestions: string[];
  day_label: string;
  purse: Purse;
}

/** The receipt for an executed decision. */
export interface TradeCard {
  kind: 'trade';
  seq: number;
  beat: DecisionBeat;
  action: TradeAction;
  amount_eur: number;
  day_label: string;
  purse: Purse;
}

export interface DecisionEntry {
  seq: number;
  beat: DecisionBeat;
  story_day: number;
  day_label: string;
  /** The player's own words. */
  text: string;
  /** 'loss' is damage taken out of the invested coins (text is its reason, not the player's words). */
  action: TradeAction | 'loss';
  amount_eur: number;
  cash_after_eur: number;
  /** Why the player chose it, in their own words; null when none was given. */
  reasoning?: string | null;
  reasoning_source?: 'inline' | 'asked' | 'commit' | 'skipped' | null;
  /** After the lock only: what this decision did to the final result, in euros. */
  effect_eur?: number;
}

/** POST /lock and GET /reveal return the same Outcome (lock is idempotent). */
export interface LockResponse {
  locked_at: string;
  horizon_days: number;
  horizon_label?: string;
  time_skip_label?: string;
  action?: DecisionAction;
  amount_eur?: number | null;
  investment_return_pct?: number;
  phase?: CampaignPhase;
  /** Every decision of the campaign with its effect on the result. */
  decisions?: DecisionEntry[];
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
  horizon_label?: string;
  time_skip_label?: string;
  action?: DecisionAction;
  amount_eur?: number | null;
  investment_return_pct?: number;
  phase?: CampaignPhase;
  /** Every decision of the campaign with its effect on the result. */
  decisions?: DecisionEntry[];
}

export interface WhatIfRow {
  key: 'dont_invest' | 'first' | 'half' | 'all' | 'spread' | 'yours';
  label: string;
  final_value: number;
  pct: number;
  hp_after?: number;
  is_yours: boolean;
}

export interface DebriefData {
  sound_reasoning: string;
  /** Comment on the quality of the player's stated reasoning (separate from luck and outcome). */
  how_you_reasoned?: string;
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

export type ArtStatus = 'placeholder' | 'pending' | 'ready' | 'failed';

/** The one character that lives at a generated location. */
export interface LocationNpc {
  id: string;
  name: string;
  role: string;
}

export interface PlayLocation {
  id: string;
  /** tavern | market_square | library for the fixed ones; a slug for campaign locations */
  key: string;
  name: string;
  description: string;
  fixed: boolean;
  art_status: ArtStatus;
  visited: boolean;
  /** The NPC who lives here (generated locations); null or absent elsewhere. */
  npc?: LocationNpc | null;
  /** True for a location the Campaign Master created mid-story. */
  generated?: boolean;
}

export interface BacklogEntry {
  seq: number;
  /** "You", "You (to Buddy)", "Campaign Master", "CommerzBuddy" or a character name */
  speaker: string;
  text: string;
  /** "npc" for a character's line (set on the curious trader's entries). */
  speaker_kind?: SpeakerKind;
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
  status?: 'active' | 'finished';
  version?: number;
  checkpoint?: string;
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
  suggestions: string[];
  characters?: { id: string; name: string; role: string; location: string | null }[];
  rumours?: string[];
  outcome?: OutcomeReveal;
  scenario?: {
    title: string;
    company_name: string;
    trade: string;
    horizon_label: string;
    budget_eur: number;
    currency?: string;
    spread_available?: boolean;
  };
  // Fields used by the commit-to-finish screens (spec 003 slice 7).
  budget_eur: number;
  horizon_days: number;
  offers_spread: boolean;
  commit_draft?: Partial<CommitDraft> | null;
  purse?: Purse;
  market_scene?: MarketScene | null;
  /** The curious trader asked "why?" about the last decision and waits for the next message. */
  awaiting_reasoning?: boolean;
  decisions?: DecisionEntry[];
  xp?: XpResult;
  debrief?: DebriefData;
}

export interface CreateCampaignRequest {
  interests: Interest[];
  /** A personal quest chosen on the Finance Quest card; omitted -> the server's default pick. */
  scenario_id?: string;
}

// ---- personal quests (mock transactions -> per-company generated quests) ----

export interface Transaction {
  date: string;
  merchant: string;
  /** Decimal string, negative for spending. */
  amount_eur: string;
  category: string;
  category_label: string;
}

export type QuestJobStatus = 'queued' | 'running' | 'ready' | 'rejected' | 'failed';

/** A generated quest. Names only the spending category, never the company behind it. */
export interface QuestJob {
  id: string;
  kind: 'daily' | 'extra';
  quest_date: string;
  category: string;
  category_label: string;
  status: QuestJobStatus;
  /** Player-safe progress label, e.g. "Researching the story". */
  step: string;
  /** Set only when the quest is ready. */
  scenario_id: string | null;
  created_at: string;
}

// ---- SSE events (tech §2.5) ----

export type DmEvent =
  | { event: 'status'; data: { state: string } }
  | { event: 'token'; data: { text: string } }
  | { event: 'speaker'; data: { speaker?: string | null; speaker_kind?: SpeakerKind | null } }
  | { event: 'card'; data: { kind: 'dice' | 'news' | 'market' | 'trade'; [field: string]: unknown } }
  | { event: 'state'; data: { can_decide?: boolean; art_ready?: string[]; [field: string]: unknown } }
  | { event: 'done'; data: { text: string; audio_text_id?: number | string | null; [field: string]: unknown } }
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
  framing?: string;
  framing_audio_text_id?: number | null;
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
export interface HpChange {
  /** Negative: HP lost (1 HP = €10). */
  delta: number;
  reason: string;
  hp: number;
  hp_eur: number;
}

/** A place the Campaign Master created mid-story; the player has already moved there. */
export interface NewLocation {
  id: string;
  key: string;
  name: string;
  description: string;
  art_status: ArtStatus;
  npc: LocationNpc;
}

export type SpeakerKind = 'npc' | 'master' | 'buddy';

/** The curious trader's question after a decision whose reasoning is missing or thin. */
export interface ReasoningPrompt {
  speaker: string;
  role: string;
  text: string;
}

export interface TurnExtras {
  speaker?: string;
  speaker_kind?: SpeakerKind;
  /** The Campaign Master took over from the NPC in this reply. */
  escalated?: boolean;
  hp_change?: HpChange | null;
  new_location?: NewLocation | null;
  suggestions?: string[];
  show_decide?: boolean;
  awaiting_reasoning?: boolean;
  reasoning_prompt?: ReasoningPrompt | null;
  location?: { id: string; key: string; name: string };
  first_visit?: boolean;
  news_text?: string;
  can_decide?: boolean;
  hint_location?: string | null;
  roll_id?: string;
  mood?: string;
  degraded?: boolean;
  replayed?: boolean;
}

export interface JournalEntry {
  seq: number;
  type: string;
  [field: string]: unknown;
}
