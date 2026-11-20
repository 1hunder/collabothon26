export interface Account {
  readonly id: string
  readonly name: string
  readonly balance: number
  readonly number: string
}

export interface Depot {
  readonly name: string
  readonly value: number
}

export interface Persona {
  readonly firstName: string
  readonly accounts: readonly Account[]
  readonly depot: Depot
}

export const persona: Persona = {
  firstName: 'Lena',
  accounts: [
    { id: 'startkonto', name: 'StartKonto', balance: 1240.5, number: 'DE00 0000 0000 0000 0000 00' },
  ],
  depot: { name: 'StartDepot', value: 0 },
}

export function totalBalance(p: Persona = persona): number {
  return p.accounts.reduce((sum, account) => sum + account.balance, 0)
}
