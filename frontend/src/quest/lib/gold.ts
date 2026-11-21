/** The quest's one currency label: gold pieces ("gp"). Every rendered amount in the quest goes through here. */
export const GOLD_SHORT = 'gp';
export const GOLD_LONG = 'gold pieces';

/** Grouped number (1,250 or 1,250.5), no currency. */
export function formatGoldNumber(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

/** "1,250 gp". */
export function formatGold(n: number): string {
  return `${formatGoldNumber(n)} ${GOLD_SHORT}`;
}
