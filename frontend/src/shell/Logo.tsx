import logo from '../assets/commerzbank-logo.png';

export default function Logo({ className = 'h-6' }: { className?: string }): React.JSX.Element {
  return <img src={logo} alt="Commerzbank" className={`w-auto ${className}`} />;
}
