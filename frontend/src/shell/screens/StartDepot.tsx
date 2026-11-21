import { useLocation, useNavigate } from 'react-router-dom';
import QuestCard from '../components/QuestCard';
import { persona } from '../data/persona';
import { formatEur } from '../lib/money';
import { useToast } from '../useToast';

const productFacts: readonly string[] = [
  'No custody fees up to €20,000 depot value',
  'Savings plans from €25 a month',
  'For pupils, students and trainees',
];

export default function StartDepot(): React.JSX.Element {
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const showToast = (): void => toast.show();
  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <p className="text-sm text-petrol-muted">Depot value</p>
        <p className="text-3xl font-semibold text-petrol">{formatEur(persona.depot.value)}</p>
      </div>
      <p className="text-petrol">You don't have any investments yet.</p>
      <ul className="flex flex-col gap-1 text-sm text-petrol-muted">
        {productFacts.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <QuestCard
        variant="depot"
        onStart={(path) => void navigate(path, { state: { origin: location.pathname } })}
        onContinue={(path) => void navigate(path, { state: { origin: location.pathname } })}
      />
      <button
        type="button"
        onClick={showToast}
        className="self-start rounded-pill bg-petrol px-6 py-2 text-sm font-semibold text-white"
      >
        Set up savings plan
      </button>
    </div>
  );
}
