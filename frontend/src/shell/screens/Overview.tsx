import { CornerUpRight } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import AccountCard from '../components/AccountCard';
import PersonalQuests from '../components/PersonalQuests';
import QuestCard from '../components/QuestCard';
import QuickActions from '../components/QuickActions';
import RecentTransactions from '../components/RecentTransactions';
import { persona, totalBalance } from '../data/persona';
import { formatEur } from '../lib/money';
import { useToast } from '../useToast';
import { startQuest, useQuestMeta } from '../../quest/questStore';

export default function Overview(): React.JSX.Element {
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { inProgress } = useQuestMeta();
  const showToast = (): void => toast.show();
  const openQuest = (path = '/quest'): void => void navigate(path, { state: { origin: location.pathname } });
  return (
    <div className="min-h-dvh bg-[#f1f4f5] text-petrol">
      <section className="bg-white px-5 pb-2 pt-4" aria-labelledby="overview-heading">
        <h1 id="overview-heading" className="text-sm font-medium text-petrol">Hello, {persona.firstName}</h1>
        <div className="mt-4">
          <p className="text-xl leading-tight">Total balance</p>
          <p className="mt-1 text-[2rem] font-bold leading-tight tracking-tight tabular-nums">{formatEur(totalBalance())}</p>
        </div>
        <div className="mb-2 mt-1 flex justify-end">
          <button type="button" onClick={showToast} className="flex min-h-11 items-center gap-2.5 rounded-full text-sm font-semibold">
            Transfer
            <span className="grid size-11 place-items-center rounded-full bg-brand-yellow">
              <CornerUpRight aria-hidden="true" size={22} />
            </span>
          </button>
        </div>
        {persona.accounts.map((a) => (
          <AccountCard layout="row" key={a.id} name={a.name} amount={formatEur(a.balance)} detail={a.number} onClick={showToast} />
        ))}
        <AccountCard
          layout="row"
          name={persona.depot.name}
          amount={formatEur(persona.depot.value)}
          detail="No investments yet"
          onClick={() => navigate('/investments/startdepot')}
        />
      </section>
      <QuickActions />
      <div className="flex flex-col gap-4 px-4 py-4">
        <QuestCard
          variant="overview"
          onStart={openQuest}
          onContinue={(path) => void navigate(path, { state: { origin: location.pathname } })}
        >
          <PersonalQuests
            busy={inProgress}
            onPlay={() => {
              startQuest();
              openQuest();
            }}
          />
        </QuestCard>
        <RecentTransactions />
      </div>
    </div>
  );
}
