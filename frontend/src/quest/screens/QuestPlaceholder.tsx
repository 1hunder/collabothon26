interface QuestPlaceholderProps {
  title: string;
}

/** Stand-in until the screen's own task lands; keeps routing testable. */
export default function QuestPlaceholder({ title }: QuestPlaceholderProps): React.JSX.Element {
  return <h1 className="font-quest-title text-3xl text-quest-gilt">{title}</h1>;
}
