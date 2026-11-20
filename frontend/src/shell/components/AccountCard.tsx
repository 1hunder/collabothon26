interface AccountCardProps {
  name: string;
  amount: string;
  detail: string;
  onClick: () => void;
}

export default function AccountCard({ name, amount, detail, onClick }: AccountCardProps): React.JSX.Element {
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
