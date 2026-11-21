import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { patchCampaignCache, queryKeys, saveCommitDraft, useCampaign, useHero } from '../../api/campaign';
import { request } from '../../api/client';
import type { CampaignState, DiceCard, DiceMode, NewsCard, PlayLocation, RollResult, TurnExtras } from '../../api/types';
import { useDmStream, type DmDone } from '../../api/useDmStream';
import { useVoice } from '../../voice';
import { inertVoice } from '../../voice/context';
import Backlog from './Backlog';
import BreakingNewsCard from './BreakingNewsCard';
import BuddyMascot from './BuddyMascot';
import BuddyScene from './BuddyScene';
import { normalizeCard } from './cards';
import ChoiceList from './ChoiceList';
import DialogueBox, { DM_NAME, type VoiceKind } from './DialogueBox';
import DiceMoment, { type DiceApi } from './DiceMoment';
import Dock from './Dock';
import HeroStatus from './HeroStatus';
import { useReportSheetOpen } from '../sheetOpen';
import JournalSheet from './JournalSheet';
import LibraryScroll from './LibraryScroll';
import MapSheet from './MapSheet';
import MarketPanel from './MarketPanel';
import NoticeBoard from './NoticeBoard';
import HotspotLayer from './HotspotLayer';
import type { HotspotTarget } from './sceneHotspots';
import RumourLedger from './RumourLedger';
import { hasRumourLedger, rumoursHeard } from './rumours';
import TitleCard from './TitleCard';
import VnStage from './VnStage';

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
  text: string;
  suggestions: readonly string[];
  showDecide: boolean;
  cards: (DiceCard | NewsCard)[];
  newsText: string | null;
  instant: boolean;
  audioTextId: number | string | null;
}

type Overlay =
  | { kind: 'none' }
  | { kind: 'timeskip'; card: NewsCard }
  | { kind: 'news'; card: NewsCard }
  | { kind: 'dice'; card: DiceCard };

type SheetName = 'map' | 'journal' | 'backlog' | 'board' | 'library' | 'rumours' | 'notice' | null;

interface TitleInfo {
  name: string;
}

const notYou = (speaker: string): boolean => !speaker.startsWith('You') && speaker !== 'CommerzBuddy';

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
  const [overlay, setOverlay] = useState<Overlay>({ kind: 'none' });
  const [sheet, setSheet] = useState<SheetName>(null);
  useReportSheetOpen(sheet !== null);
  const [buddyOpen, setBuddyOpen] = useState(false);
  const [title, setTitle] = useState<TitleInfo | null>(null);

  const latest = useRef(c);
  useEffect(() => {
    latest.current = c;
  });
  const refresh = useCallback((): void => {
    void qc.invalidateQueries({ queryKey: queryKeys.campaign(id) });
  }, [qc, id]);

  const opening = useRef(false);
  // Every finished reply becomes the scene; its extras say who spoke, what to offer, what happened.
  const onTurnDone = (done: DmDone): void => {
    const x = done.extras as TurnExtras;
    setScene({
      key: done.clientMsgId,
      speaker: x.speaker ?? DM_NAME,
      text: done.text,
      suggestions: x.suggestions ?? [],
      showDecide: x.show_decide === true,
      cards: done.cards.flatMap((raw) => normalizeCard(raw) ?? []),
      newsText: x.news_text ?? null,
      instant: false,
      audioTextId: done.extras.audio_text_id as number | string | null | undefined ?? null,
    });
    if (x.location) {
      patchCampaignCache(qc, id, { current_location_id: x.location.id });
      if (x.first_visit === true) setTitle({ name: x.location.name });
    } else if (opening.current) {
      opening.current = false;
      setTitle({ name: 'Tavern' });
    }
    refresh();
  };

  const dm = useDmStream(`${base}/actions`, onTurnDone);
  const buddy = useDmStream(`${base}/buddy`);

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
    };
  })();
  const activeOverlay: Overlay = overlay.kind === 'none' && pendingCard ? { kind: 'dice', card: pendingCard } : overlay;

  const resumed = useMemo<Scene | null>(() => {
    const last = [...c.backlog].reverse().find((e) => notYou(e.speaker));
    if (!last) return null;
    return {
      key: `resume-${last.seq}`,
      speaker: last.speaker,
      text: last.text,
      suggestions: c.suggestions ?? [],
      showDecide: false,
      cards: [],
      newsText: null,
      instant: true,
      audioTextId: null,
    };
  }, [c.backlog, c.suggestions]);

  const current = scene ?? (dm.state.phase === 'idle' ? resumed : null);
  const location = c.locations.find((l) => l.id === c.current_location_id);
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
    if (news) setOverlay({ kind: 'timeskip', card: news });
    else if (dice) setOverlay({ kind: 'dice', card: dice });
    else setAdvancedKey(current.key);
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
      setScene({ ...current, key: `${current.key}-news`, text: followUp, cards: [], newsText: null, showDecide: false, instant: false, audioTextId: null });
    } else {
      setScene({ ...current, cards: [] });
      setAdvancedKey(current.key);
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

  const bonusLead = async (): Promise<void> => {
    try {
      const card = normalizeCard(await request<Record<string, unknown>>('POST', `${base}/focus/bonus-lead`));
      refresh();
      if (card?.kind === 'dice') setOverlay({ kind: 'dice', card });
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
          speaker={DM_NAME}
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
          suggestions={current.suggestions}
          canDecide={c.can_decide || current.showDecide}
          focusLeft={c.focus_left}
          bonusLeadAvailable={c.bonus_lead_available}
          onSend={sendAction}
          onDecide={() => void decide()}
          onHint={() => {
            stopVoice();
            dm.send({}, `${base}/focus/hint`);
          }}
          onBonusLead={() => void bonusLead()}
        />
      );
    }
    return (
      <DialogueBox
        key={current.key}
        speaker={current.speaker}
        text={current.text}
        instant={current.instant}
        audioTextId={current.audioTextId}
        onAdvance={activeOverlay.kind === 'none' ? advance : () => undefined}
        onPageShown={onPageShown}
        onSwipeDown={() => setSheet('backlog')}
      />
    );
  })();

  const masterSpeaking = state.phase === 'sending' || state.phase === 'streaming' ||
    (state.phase !== 'lost' && !inChoices && current?.speaker === DM_NAME);
  const showMascot = masterSpeaking && !sheet && activeOverlay.kind === 'none';

  const openHotspot = (t: HotspotTarget): void => {
    stopVoice();
    setSheet(t === 'library' ? 'library' : t === 'market' ? 'board' : 'notice');
  };

  const chips =
    locKey === 'market_square' ? (
      <>
        <Chip label="Price board" onClick={() => setSheet('board')} />
        {hasRumourLedger(c.hero.items, c.rumours) ? <Chip label="Rumour ledger" onClick={() => setSheet('rumours')} /> : null}
      </>
    ) : locKey === 'library' ? (
      <Chip label="Library documents" onClick={() => setSheet('library')} />
    ) : locKey === 'tavern' ? (
      <Chip label="Notice board" onClick={() => setSheet('notice')} />
    ) : null;

  return (
    <VnStage
      location={location}
      status={<HeroStatus campaign={c} onOpen={() => void navigate('/quest/hero')} />}
      chips={chips}
      hotspots={
        <HotspotLayer
          locationKey={locKey}
          active={sheet === null && !buddyOpen && !diceOpen && activeOverlay.kind === 'none' && title === null && (state.phase === 'idle' || state.phase === 'done')}
          onOpen={openHotspot}
        />
      }
      dock={
        <Dock
          mapDisabled={diceOpen}
          voiceOn={voice}
          buddyOpen={buddyOpen}
          onMap={() => setSheet('map')}
          onJournal={() => setSheet('journal')}
          onBuddy={() => {
            stopVoice();
            setBuddyOpen((o) => !o);
          }}
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
          {sheet === 'notice' ? <NoticeBoard campaign={c} campaignId={id} onClose={() => setSheet(null)} /> : null}
          {sheet === 'library' ? <LibraryScroll library={c.library} onClose={() => setSheet(null)} /> : null}
          {title !== null && activeOverlay.kind === 'none' ? <TitleCard title={title.name} onDone={dismissTitle} /> : null}
          {activeOverlay.kind === 'timeskip' ? (
            <TitleCard title={activeOverlay.card.time_skip_label} onDone={() => setOverlay({ kind: 'news', card: activeOverlay.card })} />
          ) : null}
          {activeOverlay.kind === 'news' ? <BreakingNewsCard card={activeOverlay.card} onContinue={afterNews} /> : null}
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
      {buddyOpen ? (
        <BuddyScene stream={buddy} onClose={() => { stopVoice(); setBuddyOpen(false); }} onPageShown={onPageShown} onAsked={stopVoice} screen={locKey === 'market_square' || locKey === 'library' ? locKey : undefined} />
      ) : (
        <div className="relative">
          {dialogue}
          {showMascot && <BuddyMascot onArrive={() => { stopVoice(); setBuddyOpen(true); }} />}
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
