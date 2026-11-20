import { useLocation, useNavigate } from 'react-router-dom';
import AccountCard from '../components/AccountCard';
import QuestCard from '../components/QuestCard';
import QuickActions from '../components/QuickActions';
import { persona, totalBalance } from '../data/persona';
import { formatEur } from '../lib/money';
import { useToast } from '../useToast';

export default function Overview(): React.JSX.Element {
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const showToast = (): void => toast.show();
  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-2xl font-semibold text-petrol">Hello, {persona.firstName}</h1>
      <div>
        <p className="text-sm text-petrol-muted">Total balance</p>
        <p className="text-3xl font-semibold text-petrol">{formatEur(totalBalance())}</p>
      </div>
      {persona.accounts.map((a) => (
        <AccountCard key={a.id} name={a.name} amount={formatEur(a.balance)} detail={a.number} onClick={showToast} />
      ))}
      <AccountCard
        name={persona.depot.name}
        amount={formatEur(persona.depot.value)}
        detail="No investments yet"
        onClick={() => navigate('/investments/startdepot')}
      />
      <QuickActions />
      <QuestCard
        variant="overview"
        onStart={() => void navigate('/quest', { state: { origin: location.pathname } })}
        onContinue={(path) => void navigate(path, { state: { origin: location.pathname } })}
      />
    </div>
  );
}
