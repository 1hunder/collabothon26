import { useNavigate } from 'react-router-dom';
import AccountCard from '../components/AccountCard';
import { persona } from '../data/persona';
import { formatEur } from '../lib/money';

export default function Investments(): React.JSX.Element {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col gap-4 p-4">
      <AccountCard
        name={persona.depot.name}
        amount={formatEur(persona.depot.value)}
        detail="Depot"
        onClick={() => navigate('/investments/startdepot')}
      />
    </div>
  );
}
