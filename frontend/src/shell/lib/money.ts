const eurFormatter = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' })

export function formatEur(amount: number): string {
  return eurFormatter.format(amount)
}
