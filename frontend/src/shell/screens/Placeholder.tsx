import { useMatches } from 'react-router-dom';
import { isShellRouteHandle } from '../routeHandle';

export default function Placeholder({ title }: { title?: string }): React.JSX.Element {
  const matches = useMatches();
  const routeTitle = [...matches]
    .reverse()
    .map((m) => (isShellRouteHandle(m.handle) ? m.handle.title : undefined))
    .find((t) => t !== undefined);
  const shown = title ?? routeTitle;
  return (
    <section className="p-4">
      {shown ? <h2 className="sr-only">{shown}</h2> : null}
      <p className="text-petrol-muted">This area isn't part of the demo.</p>
    </section>
  );
}
