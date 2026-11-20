import { CreditCard, Mail, Send } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useToast } from '../useToast';

const actions: readonly { label: string; Icon: LucideIcon }[] = [
  { label: 'Transfer', Icon: Send },
  { label: 'Cards', Icon: CreditCard },
  { label: 'Postbox', Icon: Mail },
];

export default function QuickActions(): React.JSX.Element {
  const toast = useToast();
  return (
    <div className="grid grid-cols-3 gap-3">
      {actions.map(({ label, Icon }) => (
        <button
          key={label}
          type="button"
          onClick={() => toast.show()}
          className="flex flex-col items-center gap-2 rounded-card bg-warm py-3 text-sm font-medium text-petrol"
        >
          <Icon aria-hidden="true" size={22} />
          {label}
        </button>
      ))}
    </div>
  );
}
