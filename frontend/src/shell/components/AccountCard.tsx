import logo from '../../assets/commerzbank-logo.png';

interface AccountCardProps {
  layout?: 'card' | 'row';
  name: string;
  amount: string;
  detail: string;
  onClick: () => void;
}

export default function AccountCard({ layout = 'card', name, amount, detail, onClick }: AccountCardProps): React.JSX.Element {
  if (layout === 'row') {
    return (
      <button type="button" onClick={onClick}
        className="grid min-h-[72px] w-full grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-x-3 bg-white py-2.5 text-left text-petrol">
        <span aria-hidden="true" className="grid size-11 place-items-center rounded-lg bg-petrol">
          <span
            className="h-7 w-7 bg-no-repeat"
            style={{ backgroundImage: `url(${logo})`, backgroundPosition: 'right -4px center', backgroundSize: '174px auto' }}
          />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold">{name}</span>
          <span className="mt-0.5 block text-xs leading-4 text-petrol-muted">{detail}</span>
        </span>
        <span className="self-center whitespace-nowrap text-sm font-semibold tabular-nums">{amount}</span>
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full flex-col gap-1 rounded-card border border-line bg-white p-4 text-left text-petrol"
    >
      <span className="text-sm font-medium text-petrol-muted">{name}</span>
      <span className="text-xl font-semibold">{amount}</span>
      <span className="break-words text-xs text-petrol-muted">{detail}</span>
    </button>
  );
}
