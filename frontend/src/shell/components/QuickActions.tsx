import { CreditCard, Mail } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useToast } from '../useToast';

const actions: readonly { label: string; Icon: LucideIcon }[] = [
  { label: 'Cards', Icon: CreditCard },
  { label: 'Postbox', Icon: Mail },
];

export default function QuickActions(): React.JSX.Element {
  const toast = useToast();
  return (
    <section aria-labelledby="quick-actions-title" className="mt-1.5 bg-white px-5 pb-4 pt-4">
      <h2 id="quick-actions-title" className="text-base font-semibold">Quick actions</h2>
      <div className="mt-3 flex gap-4">
        {actions.map(({ label, Icon }) => (
          <button
            key={label}
            type="button"
            onClick={() => toast.show()}
            className="flex min-w-16 flex-col items-center gap-1.5 rounded-lg text-xs font-medium text-petrol"
          >
            <span className="grid size-12 place-items-center rounded-full border border-line">
              <Icon aria-hidden="true" size={22} strokeWidth={1.7} />
            </span>
            {label}
          </button>
        ))}
      </div>
    </section>
  );
}
