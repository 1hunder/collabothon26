import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { patchCampaignCache, queryKeys, saveCommitDraft, useCampaign, useHero } from '../../api/campaign';
import { request } from '../../api/client';
import type { CampaignState, DiceCard, DiceMode, HpChange, MarketCard, NewsCard, PlayLocation, RollResult, SpeakerKind, TradeCard, TurnExtras } from '../../api/types';
import { useDmStream, type DmDone } from '../../api/useDmStream';
import { VETERAN_TALK_PATH, useVeteran, veteranKeys } from '../../api/veteran';
import { useVoice } from '../../voice';
import { inertVoice } from '../../voice/context';
import Backlog from './Backlog';
import BreakingNewsCard from './BreakingNewsCard';
import BuddyMascot from './BuddyMascot';
import BuddyScene from './BuddyScene';
import { normalizeCard, type OfferMomentCard, type QuestCard } from './cards';
import { MarketMoment, OfferMoment, TradeReceipt, offerTerms } from './DecisionCards';
import ChoiceList from './ChoiceList';
import DialogueBox, { DM_NAME, type VoiceKind } from './DialogueBox';
import DiceMoment, { type DiceApi } from './DiceMoment';
import Dock from './Dock';
import { useEdu } from './useEdu';
import type { EduMoment } from '../../api/types';
import HeroStatus from './HeroStatus';
import { useReportSheetOpen } from '../sheetOpen';
import JournalSheet from './JournalSheet';
import LibraryScroll from './LibraryScroll';
import MapSheet from './MapSheet';
import MarketPanel from './MarketPanel';
import HotspotLayer from './HotspotLayer';
import type { HotspotTarget } from './sceneHotspots';
import RumourLedger from './RumourLedger';
import { hasRumourLedger, rumoursHeard } from './rumours';
import TavernVeteran from './TavernVeteran';
import TitleCard from './TitleCard';
import VeteranScene, { VeteranChip } from './VeteranScene';
import VeteranTimeline from './VeteranTimeline';
import VnStage from './VnStage';
import { formatGold } from '../lib/gold';

export interface PlayScreenProps {
  /** Voice toggle state. Left out, the screen keeps its own (the voice module owns it later). */
  voiceOn?: boolean;
  onToggleVoice?: () => void;
  /** VOICE HOOK: called once per page when it starts to show. */
  onPageShown?: (text: string, voice: VoiceKind, audioTextId?: number | string | null) => void;
}

interface Scene {
  key: string;
  speaker: string;
  speakerKind?: SpeakerKind;
  /** The Campaign Master took over from the NPC in this reply. */
  escalated?: boolean;
  text: string;
  /** The curious trader's question: one more page after the Master's reply. */
  trader?: { speaker: string; text: string } | null;
  suggestions: readonly string[];
  showDecide: boolean;
  cards: QuestCard[];
  newsText: string | null;
  instant: boolean;
  audioTextId: number | string | null;
  /** The all-in plot moved to its finish: once this reply is read, the outcome opens. */
  fastForward?: boolean;
}

type Overlay =
  | { kind: 'none' }
  | { kind: 'timeskip'; card: NewsCard }
  | { kind: 'news'; card: NewsCard }
  | { kind: 'dice'; card: DiceCard }
  | { kind: 'market'; card: MarketCard }
  | { kind: 'offer'; card: OfferMomentCard }
  | { kind: 'trade'; card: TradeCard };

type SheetName = 'map' | 'journal' | 'backlog' | 'board' | 'library' | 'rumours' | 'timeline' | null;

interface TitleInfo {
  name: string;
}

/** How long a new location's art may stay pending before the plain backdrop takes over. */
export const ART_TIMEOUT_MS = 90_000;
export const ART_POLL_MS = 4_000;
const DAMAGE_TOAST_MS = 6_000;

interface DamageToast {
  key: number;
  text: string;
}

const damageText = (h: HpChange): string => `−${Math.abs(h.delta)} HP (−${formatGold(Math.abs(h.delta) * 10)}): ${h.reason}`;

const notYou = (speaker: string): boolean => !speaker.startsWith('You') && speaker !== 'CommerzBuddy';
const TAVERN = 'tavern';

export default function PlayScreen({ voiceOn, onToggleVoice, onPageShown }: PlayScreenProps): React.JSX.Element {
  const hero = useHero();
  const id = hero.data?.active_campaign_id ?? '';
  const campaign = useCampaign(id);
  const c = campaign.data;
  if (!c) return <p role="status" className="p-4">Loading…</p>;
  return <Play key={id} c={c} id={id} voiceOn={voiceOn} onToggleVoice={onToggleVoice} onPageShown={onPageShown} />;
}

interface PlayProps extends PlayScreenProps {
  c: CampaignState;
  id: string;
}

function Play({ c, id, voiceOn, onToggleVoice, onPageShown: onPageShownProp }: PlayProps): React.JSX.Element {
  const voiceApi = useVoice();
  const hasProvider = voiceApi !== inertVoice;
  const { stop: stopVoice, onPageShown: voicePage } = voiceApi;
  const onPageShown = useCallback(
    (text: string, voice: VoiceKind, audioTextId?: number | string | null): void => {
      if (onPageShownProp) onPageShownProp(text, voice, audioTextId);
      else voicePage(text, voice, audioTextId == null ? null : String(audioTextId));
    },
    [onPageShownProp, voicePage],
  );
  const qc = useQueryClient();
  const navigate = useNavigate();
  const base = `/campaigns/${id}`;
  const [localVoice, setLocalVoice] = useState(true);
  const [scene, setScene] = useState<Scene | null>(null);
  const [advancedKey, setAdvancedKey] = useState<string | null>(null);
  // The reply brought back with "Read again": shown silently, and its last tap returns to the input.
  const [rereadKey, setRereadKey] = useState<string | null>(null);
  const [overlay, setOverlay] = useState<Overlay>({ kind: 'none' });
  const [sheet, setSheet] = useState<SheetName>(null);
  useReportSheetOpen(sheet !== null);
  const [buddyOpen, setBuddyOpen] = useState(false);
  // The Veteran by the Tavern fire: hero-scoped, it never spends a turn of this campaign.
  const [veteranOpen, setVeteranOpen] = useState(false);
  const [timelineFor, setTimelineFor] = useState<string | null>(null);
  const [title, setTitle] = useState<TitleInfo | null>(null);
  // A location the Master just created: its art is awaited until ready, failed or timed out.
  const [exploreId, setExploreId] = useState<string | null>(null);
  const [damage, setDamage] = useState<DamageToast | null>(null);
  const [hitKey, setHitKey] = useState(0);

  const latest = useRef(c);
  useEffect(() => {
    latest.current = c;
  });
  const refresh = useCallback((): void => {
    void qc.invalidateQueries({ queryKey: queryKeys.campaign(id) });
  }, [qc, id]);

  useEffect(() => {
    if (damage === null) return;
    const t = window.setTimeout(() => setDamage(null), DAMAGE_TOAST_MS);
    return () => window.clearTimeout(t);
  }, [damage]);

  const opening = useRef(false);
  // Every finished reply becomes the scene; its extras say who spoke, what to offer, what happened.
  const edu = useEdu(id);
  const onTurnDone = (done: DmDone): void => {
    edu.announce(done.extras.edu_new as EduMoment[] | undefined);
    const x = done.extras as TurnExtras;
    setScene({
      key: done.clientMsgId,
      speaker: x.speaker ?? DM_NAME,
      speakerKind: x.speaker_kind,
      escalated: x.escalated === true,
      text: done.text,
      trader: x.reasoning_prompt ? { speaker: x.reasoning_prompt.speaker, text: x.reasoning_prompt.text } : null,
      suggestions: x.suggestions ?? [],
      showDecide: x.show_decide === true,
      fastForward: x.fast_forward === true,
      cards: done.cards.flatMap((raw) => normalizeCard(raw) ?? []),
      newsText: x.news_text ?? null,
      instant: false,
      audioTextId: done.extras.audio_text_id as number | string | null | undefined ?? null,
    });
    patchCampaignCache(qc, id, { awaiting_reasoning: x.awaiting_reasoning === true });
    if (x.hp_change) {
      const h = x.hp_change;
      patchCampaignCache(qc, id, { hp: h.hp, hp_eur: h.hp_eur });
      setHitKey((k) => k + 1);
      setDamage({ key: Date.now(), text: damageText(h) });
    }
    const made = x.new_location;
    if (made) {
      const { npc, ...rest } = made;
      qc.setQueryData<CampaignState>(queryKeys.campaign(id), (cur) =>
        cur
          ? {
              ...cur,
              current_location_id: made.id,
              locations: cur.locations.some((l) => l.id === made.id)
                ? cur.locations
                : [...cur.locations, { ...rest, fixed: false, visited: true, npc, generated: true }],
            }
          : cur,
      );
      if (made.art_status === 'pending') setExploreId(made.id);
    } else if (x.location) {
      patchCampaignCache(qc, id, { current_location_id: x.location.id });
      if (x.first_visit === true) setTitle({ name: x.location.name });
    } else if (opening.current) {
      opening.current = false;
      setTitle({ name: 'Tavern' });
    }
    refresh();
  };

  const dm = useDmStream(`${base}/actions`, onTurnDone);
  const buddy = useDmStream(`${base}/buddy`, (d) => edu.announce(d.extras.edu_new as EduMoment[] | undefined));
  const veteran = useDmStream(VETERAN_TALK_PATH, () => void qc.invalidateQueries({ queryKey: veteranKeys.overview }));
  const veteranInfo = useVeteran(veteranOpen);

  // Opening scene: the first request of a new campaign.
  const needsOpening = c.phase === 'setup' && !c.opening_done;
  const { send: dmSend } = dm;
  useEffect(() => {
    if (!needsOpening) return;
    opening.current = true;
    dmSend({}, `${base}/opening`);
  }, [needsOpening, dmSend, base]);

  // Resuming with a roll still open: bring the dice check back (derived, no effect needed).
  const [resumeDone, setResumeDone] = useState(false);
  const pendingCard = ((): DiceCard | null => {
    const p = c.pending;
    if (!p || resumeDone || scene !== null || dm.state.phase !== 'idle') return null;
    const ch = c.challenges.find((x) => x.id === p.challenge_id);
    if (!ch) return null;
    return {
      kind: 'dice',
      roll_id: ch.id,
      challenge_id: ch.id,
      title: ch.title,
      dc: ch.dc,
      bonus: 2,
      keen_eye_available: c.hero.class === 'investigator' && c.keen_eye_left > 0,
      keen_eye_left: c.keen_eye_left,
      skill: ch.skill ?? null,
    };
  })();
  const activeOverlay: Overlay = overlay.kind === 'none' && pendingCard ? { kind: 'dice', card: pendingCard } : overlay;

  const location = c.locations.find((l) => l.id === c.current_location_id);
  const resumed = useMemo<Scene | null>(() => {
    const last = [...c.backlog].reverse().find((e) => notYou(e.speaker));
    if (!last) return null;
    return {
      key: `resume-${last.seq}`,
      speaker: last.speaker,
      text: last.text,
      speakerKind: last.speaker_kind ?? (location?.npc && last.speaker === location.npc.name ? 'npc' : undefined),
      suggestions: c.suggestions ?? [],
      showDecide: false,
      cards: [],
      newsText: null,
      instant: true,
      audioTextId: last.audio_text_id ?? null,
    };
  }, [c.backlog, c.suggestions, location?.npc]);

  const current = scene ?? (dm.state.phase === 'idle' ? resumed : null);
  const exploring = exploreId !== null && location?.id === exploreId && location.art_status === 'pending';
  useEffect(() => {
    if (exploreId === null) return;
    const poll = window.setInterval(refresh, ART_POLL_MS);
    const giveUp = window.setTimeout(() => setExploreId(null), ART_TIMEOUT_MS);
    return () => {
      window.clearInterval(poll);
      window.clearTimeout(giveUp);
    };
  }, [exploreId, refresh]);
  const npc = location?.npc ?? null;
  const diceOpen = activeOverlay.kind === 'dice' || c.pending !== null;
  const voice = voiceOn ?? (hasProvider ? voiceApi.enabled : localVoice);
  const state = dm.state;

  const sendAction = (text: string): void => {
    stopVoice();
    setAdvancedKey(null);
    dm.send({ text });
  };

  const move = (l: PlayLocation): void => {
    stopVoice();
    setSheet(null);
    setAdvancedKey(null);
    dm.send({ location_id: l.id }, `${base}/move`);
  };

  const advance = (): void => {
    if (!current) return;
    const news = current.cards.find((k): k is NewsCard => k.kind === 'news');
    const dice = current.cards.find((k): k is DiceCard => k.kind === 'dice');
    const market = current.cards.find((k): k is MarketCard => k.kind === 'market');
    const trade = current.cards.find((k): k is TradeCard => k.kind === 'trade');
    const offer = current.cards.find((k): k is OfferMomentCard => k.kind === 'offer');
    if (news) setOverlay({ kind: 'timeskip', card: news });
    else if (dice) setOverlay({ kind: 'dice', card: dice });
    else if (trade) setOverlay({ kind: 'trade', card: trade });
    else if (offer) setOverlay({ kind: 'offer', card: offer });
    else if (market) setOverlay({ kind: 'market', card: market });
    else finishScene(current);
  };

  // The decision scene: its suggestions become the choices, and the written action answers it.
  const answerScene = (card: MarketCard | OfferMomentCard): void => {
    setOverlay({ kind: 'none' });
    if (!current) return;
    const key = `${current.key}-scene`;
    const who = card.kind === 'offer' ? { speaker: card.by.name, speakerKind: 'npc' as const } : { speaker: DM_NAME, speakerKind: undefined };
    setScene({ ...current, key, ...who, text: card.text, suggestions: card.suggestions, cards: [], newsText: null, showDecide: false, instant: true, audioTextId: card.kind === 'offer' ? null : card.audio_text_id ?? null });
    setAdvancedKey(key);
  };

  // After a receipt: the decision scene of the same reply if the engine opened one, else the choices.
  // The end of a reply's pages: the curious trader's question (if any) is one more page, then the choices.
  const finishScene = (cur: Scene): void => {
    if (cur.fastForward) {
      // Nothing was left at stake: the story went on to its finish, the outcome opens as after a lock.
      patchCampaignCache(qc, id, { phase: 'timeskip' });
      void navigate('/quest/outcome', { replace: true });
      return;
    }
    if (cur.trader) {
      setScene({ ...cur, key: `${cur.key}-trader`, speaker: cur.trader.speaker, speakerKind: 'npc', escalated: false, text: cur.trader.text, trader: null, cards: [], newsText: null, showDecide: false, instant: false, audioTextId: null });
    } else {
      setAdvancedKey(cur.key);
    }
  };

  const afterTrade = (): void => {
    if (!current) return;
    const market = current.cards.find((k): k is MarketCard => k.kind === 'market');
    const offer = current.cards.find((k): k is OfferMomentCard => k.kind === 'offer');
    if (offer) setOverlay({ kind: 'offer', card: offer });
    else if (market) setOverlay({ kind: 'market', card: market });
    else {
      setOverlay({ kind: 'none' });
      finishScene(current);
    }
  };

  // After the news cards: the dice check of the same turn, else the Campaign Master's follow-up.
  const afterNews = (): void => {
    if (!current) return;
    const dice = current.cards.find((k): k is DiceCard => k.kind === 'dice');
    if (dice) {
      setOverlay({ kind: 'dice', card: dice });
      return;
    }
    setOverlay({ kind: 'none' });
    const followUp =
      current.newsText ??
      [...latest.current.backlog].reverse().find((e) => notYou(e.speaker))?.text ??
      null;
    if (followUp !== null && followUp !== current.text) {
      const news = current.cards.find((k): k is NewsCard => k.kind === 'news');
      const followUpAudio = current.newsText !== null ? (news?.framing_audio_text_id ?? null) : null;
      setScene({ ...current, key: `${current.key}-news`, text: followUp, cards: [], newsText: null, showDecide: false, instant: false, audioTextId: followUpAudio });
    } else {
      setScene({ ...current, cards: [] });
      finishScene(current);
    }
  };

  const decide = async (): Promise<void> => {
    try {
      await saveCommitDraft(id, {});
      patchCampaignCache(qc, id, { phase: 'commit' });
      void navigate('/quest/commit', { replace: true });
    } catch {
      refresh();
    }
  };

  const toggleVoice = (): void => {
    if (onToggleVoice) onToggleVoice();
    else if (hasProvider) voiceApi.toggle();
    else setLocalVoice((v) => !v);
  };

  const dismissTitle = useCallback((): void => setTitle(null), []);

  const diceChallengeId = activeOverlay.kind === 'dice' ? activeOverlay.card.challenge_id : null;
  const diceApi = useMemo<DiceApi | null>(() => {
    if (diceChallengeId === null) return null;
    const challengeId = diceChallengeId;
    const done = (r: RollResult): RollResult => {
      refresh();
      return r;
    };
    return {
      roll: (mode: DiceMode) => request<RollResult>('POST', `${base}/rolls`, { challenge_id: challengeId, mode }).then(done),
      reroll: (rid: string) => request<RollResult>('POST', `${base}/rolls/${rid}/reroll`).then(done),
      accept: (rid: string) => request<RollResult>('POST', `${base}/rolls/${rid}/accept`).then(done),
    };
  }, [diceChallengeId, base, refresh]);

  const rolled = (final: RollResult): void => {
    setOverlay({ kind: 'none' });
    setResumeDone(true);
    setAdvancedKey(null);
    stopVoice();
    dm.send({ roll_id: final.roll_id }, `${base}/narrate-roll`);
  };

  const inChoices = current !== null && advancedKey === current.key;
  const locKey = location?.key;

  const dialogue = ((): React.ReactNode => {
    if (state.phase === 'lost') {
      return (
        <div role="alert" className="mx-3 rounded-lg bg-quest-lapis/95 p-4 font-quest text-quest-vellum">
          <p>The Campaign Master lost the thread.</p>
          <button type="button" onClick={dm.retry} className="mt-2 min-h-11 rounded-full border border-quest-gilt bg-quest-lapis-deep px-5 font-quest-sans font-bold text-quest-soot">
            Try again
          </button>
        </div>
      );
    }
    if (state.phase === 'sending' || state.phase === 'streaming') {
      return (
        <DialogueBox
          key={state.clientMsgId}
          // The server names the speaker before the first word; until then, at a place with an
          // NPC the NPC is the likely speaker (the Master only steps in when the NPC hands over).
          speaker={(state.phase === 'streaming' ? state.speaker : null) ?? location?.npc?.name ?? DM_NAME}
          speakerKind={
            state.phase === 'streaming' && state.speakerKind
              ? (state.speakerKind as SpeakerKind)
              : location?.npc
                ? 'npc'
                : undefined
          }
          text={state.phase === 'streaming' ? state.text : ''}
          final={false}
          writing
          onAdvance={advance}
          onPageShown={onPageShown}
          onSwipeDown={() => setSheet('backlog')}
        />
      );
    }
    if (current === null) return null;
    if (inChoices) {
      return (
        <ChoiceList
          prompt={c.offer ? `${c.offer.by.name}, ${c.offer.by.role}: ${offerTerms(c.offer)} How do you answer?` : c.market_scene ? 'What do you do with your coins?' : undefined}
          purse={c.market_scene ? c.purse : undefined}
          canDecide={!c.market_scene && (c.can_decide || current.showDecide)}
          awaitingReasoning={c.awaiting_reasoning === true}
          onSend={sendAction}
          onDecide={() => void decide()}
          onReread={current.text.trim() !== '' ? () => {
            setRereadKey(current.key);
            setAdvancedKey(null);
          } : undefined}
        />
      );
    }
    return (
      <>
        {current.escalated ? (
          <p data-testid="escalation" className="mx-3 mb-3 flex items-center gap-3 font-quest text-sm italic text-quest-vellum-dim">
            <span aria-hidden="true" className="h-px flex-1 bg-quest-gilt/40" />
            The Campaign Master steps in
            <span aria-hidden="true" className="h-px flex-1 bg-quest-gilt/40" />
          </p>
        ) : null}
        <DialogueBox
          key={current.key}
          speaker={current.speaker}
          speakerKind={current.speakerKind}
          text={current.text}
          instant={current.instant}
          audioTextId={current.audioTextId}
          revisit={rereadKey === current.key}
          onAdvance={
            rereadKey === current.key
              ? () => {
                  setRereadKey(null);
                  setAdvancedKey(current.key);
                }
              : activeOverlay.kind === 'none'
                ? advance
                : () => undefined
          }
          onPageShown={onPageShown}
          onSwipeDown={() => setSheet('backlog')}
        />
      </>
    );
  })();

  const masterSpeaking = state.phase === 'sending' || state.phase === 'streaming' ||
    (state.phase !== 'lost' && !inChoices && current?.speaker === DM_NAME);
  const showMascot = (masterSpeaking || inChoices) && !sheet && activeOverlay.kind === 'none';

  const openHotspot = (t: HotspotTarget): void => {
    stopVoice();
    setSheet(t === 'library' ? 'library' : 'board');
  };

  const npcChip =
    npc !== null ? (
      <span data-testid="npc-chip" className="inline-flex min-h-8 items-center rounded-full border border-quest-verdigris-light/60 bg-quest-soot/60 px-3 font-quest-sans text-sm text-quest-vellum">
        {npc.name} · {npc.role}
      </span>
    ) : null;
  const openVeteran = (): void => {
    stopVoice();
    setBuddyOpen(false);
    veteran.reset();
    setVeteranOpen(true);
  };
  const closeVeteran = (): void => {
    stopVoice();
    setVeteranOpen(false);
  };
  const inTavern = locKey === TAVERN;
  const sceneFree = sheet === null && !buddyOpen && !veteranOpen && !diceOpen && activeOverlay.kind === 'none' && title === null && (state.phase === 'idle' || state.phase === 'done');

  const chips =
    npcChip !== null ? (
      npcChip
    ) : locKey === 'market_square' ? (
      <>
        <Chip label="Price board" onClick={() => setSheet('board')} />
        {hasRumourLedger(c.hero.items, c.rumours) ? <Chip label="Rumour ledger" onClick={() => setSheet('rumours')} /> : null}
      </>
    ) : locKey === 'library' ? (
      <Chip label="Library documents" onClick={() => setSheet('library')} />
    ) : inTavern && !veteranOpen ? (
      <VeteranChip onClick={openVeteran} />
    ) : null;

  return (
    <VnStage
      location={location}
      exploring={exploring}
      status={<HeroStatus campaign={c} hitKey={hitKey} onOpen={() => void navigate('/quest/hero')} />}
      chips={chips}
      hotspots={
        <>
          <HotspotLayer locationKey={locKey} active={sceneFree} onOpen={openHotspot} />
          {inTavern ? <TavernVeteran active={sceneFree} hidden={veteranOpen} onOpen={openVeteran} /> : null}
        </>
      }
      dock={
        <Dock
          mapDisabled={diceOpen}
          voiceOn={voice}
          onMap={() => setSheet('map')}
          onJournal={() => setSheet('journal')}
          onToggleVoice={toggleVoice}
        />
      }
      overlays={
        <>
          {sheet === 'map' ? (
            <MapSheet locations={c.locations} currentId={c.current_location_id} disabled={diceOpen} onMove={move} onClose={() => setSheet(null)} />
          ) : null}
          {sheet === 'journal' ? (
            <JournalSheet campaignId={id} onBacklog={() => setSheet('backlog')} onClose={() => setSheet(null)} />
          ) : null}
          {sheet === 'backlog' ? <Backlog entries={c.backlog} onClose={() => setSheet(null)} /> : null}
          {sheet === 'board' ? (
            <MarketPanel rows={c.price_board} newsDay={c.news_shown ? c.story_day : null} onClose={() => setSheet(null)} />
          ) : null}
          {sheet === 'rumours' ? <RumourLedger rumours={rumoursHeard(c.rumours, c.backlog)} onClose={() => setSheet(null)} /> : null}
          {sheet === 'library' ? <LibraryScroll library={c.library} onClose={() => setSheet(null)} /> : null}
          {sheet === 'timeline' && timelineFor !== null ? <VeteranTimeline campaignId={timelineFor} onClose={() => setSheet(null)} /> : null}
          {title !== null && activeOverlay.kind === 'none' ? <TitleCard title={title.name} onDone={dismissTitle} /> : null}
          {activeOverlay.kind === 'timeskip' ? (
            <TitleCard title={activeOverlay.card.time_skip_label} onDone={() => setOverlay({ kind: 'news', card: activeOverlay.card })} />
          ) : null}
          {activeOverlay.kind === 'news' ? <BreakingNewsCard card={activeOverlay.card} onContinue={afterNews} /> : null}
          {activeOverlay.kind === 'market' ? <MarketMoment card={activeOverlay.card} onAnswer={() => answerScene(activeOverlay.card)} /> : null}
          {activeOverlay.kind === 'offer' ? <OfferMoment card={activeOverlay.card} onAnswer={() => answerScene(activeOverlay.card)} /> : null}
          {activeOverlay.kind === 'trade' ? <TradeReceipt card={activeOverlay.card} onContinue={afterTrade} /> : null}
          {activeOverlay.kind === 'dice' && diceApi ? (
            <DiceMoment
              key={activeOverlay.card.challenge_id}
              card={activeOverlay.card}
              api={diceApi}
              onResolved={rolled}
              resumeSetback={overlay.kind === 'none' && c.pending?.state === 'rolling' ? { rerollsLeft: c.rerolls_left } : undefined}
            />
          ) : null}
        </>
      }
    >
      {damage !== null ? (
        <p role="status" data-testid="damage-toast" className="pointer-events-none mx-3 mb-1 self-center rounded-full border border-quest-wax-light/70 bg-quest-wax/90 px-4 py-2 text-center font-quest-sans text-sm font-bold text-quest-vellum">
          {damage.text}
        </p>
      ) : null}
      {veteranOpen ? (
        <VeteranScene
          stream={veteran}
          overview={veteranInfo.data}
          onClose={closeVeteran}
          onTimeline={(cid) => {
            stopVoice();
            setTimelineFor(cid);
            setSheet('timeline');
          }}
          onPageShown={onPageShown}
          onAsked={stopVoice}
        />
      ) : buddyOpen ? (
        <BuddyScene edu={edu} stream={buddy} onClose={() => { stopVoice(); setBuddyOpen(false); }} onPageShown={onPageShown} onAsked={stopVoice} screen={locKey === 'market_square' || locKey === 'library' ? locKey : undefined} />
      ) : (
        <div className="relative">
          {dialogue}
          {showMascot && <BuddyMascot pending={edu.pending} poppedId={edu.poppedId} onOpenChat={() => { stopVoice(); setBuddyOpen(true); }} />}
        </div>
      )}
    </VnStage>
  );
}

function Chip({ label, onClick }: { label: string; onClick: () => void }): React.JSX.Element {
  return (
    <button type="button" onClick={onClick} className="min-h-11 rounded-full border border-quest-gilt/60 bg-quest-soot/50 px-4 font-quest-sans text-sm text-quest-gilt">
      {label}
    </button>
  );
}
