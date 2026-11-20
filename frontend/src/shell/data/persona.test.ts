import { describe, expect, it } from 'vitest'
import { persona, totalBalance } from './persona'

describe('persona', () => {
  it('totals account balances', () => {
    expect(totalBalance()).toBe(1240.5)
  })
  it('exposes the StartKonto number', () => {
    expect(persona.accounts[0].number).toBe('DE00 0000 0000 0000 0000 00')
  })
})
