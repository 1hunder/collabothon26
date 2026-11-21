import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { request } from '../../api/client';
import type { CampaignState, JournalEntry } from '../../api/types';
import { formatStoryDay } from '../lib/storyNumber';
import { newsNotices } from './newsNotices';
import { useEscapeKey } from './useEscapeKey';

interface NoticeBoardProps {
  campaign: CampaignState;
  campaignId: string;
  onClose: () => void;
}

const paper: React.CSSProperties = {
  backgroundColor: '#efe4c8',
  backgroundImage: 'radial-gradient(ellipse at 50% 0%, rgba(255,250,235,0.8), transparent 65%), repeating-linear-gradient(6deg, rgba(110,84,44,0.05) 0 2px, transparent 2px 8px)',
  boxShadow: '0 10px 28px rgba(0,0,0,0.45), inset 0 0 30px rgba(120,80,30,0.22)',
};

/** Tavern: the notice board shows the finance news that has broken so far, newest first. */
export default function NoticeBoard({ campaign: c, campaignId, onClose }: NoticeBoardProps): React.JSX.Element {
  useEscapeKey(onClose);
  const journal = useQuery({
    queryKey: ['journal', campaignId],
    queryFn: () => request<{ entries: JournalEntry[] }>('GET', `/campaigns/${campaignId}/journal`),
    staleTime: 0,
  });
  const notices = newsNotices(c, journal.data?.entries);
  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-quest-soot/70 px-4">
      <div role="dialog" aria-modal="true" aria-label="Notice board" className="relative max-h-[85%] w-full overflow-y-auto rounded-md bg-[#3b2a1a] px-4 pb-5 pt-14 shadow-[inset_0_0_0_3px_#7a5a34]">
        <button type="button" aria-label="Close Notice board" onClick={onClose} className="absolute left-2 top-2 flex h-11 w-11 items-center justify-center rounded-full text-quest-gilt">
          <X aria-hidden="true" size={22} />
        </button>
        <h2 className="absolute left-14 top-3 font-quest-title text-3xl text-quest-gilt">Notice board</h2>
        {journal.isPending && notices.length === 0 ? <p role="status" className="font-quest text-quest-vellum">Loading…</p> : null}
        <ul className="space-y-4">
          {notices.length === 0 && !journal.isPending ? (
            <li style={paper} className="rounded-sm p-5 font-quest text-lg text-quest-soot">
              No news posted yet. Check back as the days pass.
            </li>
          ) : null}
          {notices.map((n, i) => (
            <li key={n.key} style={paper} className={`relative rounded-sm px-5 pb-4 pt-6 font-quest text-quest-soot ${i % 2 === 0 ? '-rotate-1' : 'rotate-1'}`}>
              <span aria-hidden="true" className="absolute left-1/2 top-2 h-3 w-3 -translate-x-1/2 rounded-full bg-quest-wax shadow" />
              <p className="font-quest-sans text-xs font-bold uppercase tracking-widest text-quest-wax">
                {n.kind}
                {n.day !== null ? ` · ${formatStoryDay(n.day)}` : ''}
              </p>
              <h3 className="font-quest-title text-2xl leading-tight text-quest-lapis">{n.headline}</h3>
              {n.summary ? <p className="mt-1 text-[17px] leading-snug">{n.summary}</p> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
