import { describe, expect, it } from 'vitest'
import { formatEur } from './money'

describe('formatEur', () => {
  it('formats a balance with symbol, thousands separator and two decimals', () => {
    expect(formatEur(1240.5)).toBe('€1,240.50')
  })
  it('formats zero', () => {
    expect(formatEur(0)).toBe('€0.00')
  })
})
