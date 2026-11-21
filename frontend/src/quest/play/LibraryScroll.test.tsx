import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { CampaignState } from '../../api/types';
import LibraryScroll from './LibraryScroll';

const library: CampaignState['library'] = {
  company_card: { name: 'Lumenvale Guild', trade: 'Lantern oil', size: 'About 4,200 workers', key_figures: [{ id: 'b', label: 'Barrels sold', value: 1200 }] },
  documents: [
    { id: 'd1', title: 'Ledger one', entries: [{ id: 'e1', title: 'Entry', text: 'First text' }] },
    { id: 'd2', title: 'Ledger two', entries: [{ id: 'e2', title: 'Entry', text: 'Second text' }] },
  ],
} as CampaignState['library'];

describe('LibraryScroll', () => {
  it('shows the company card first, then one page per document, with a page indicator', async () => {
    const user = userEvent.setup();
    render(<LibraryScroll library={library} onClose={() => undefined} />);
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Company card' })).toHaveTextContent('Lumenvale Guild');
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    expect(screen.getByText('Ledger one')).toBeInTheDocument();
    expect(screen.queryByText('Lumenvale Guild')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Ledger two')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('pages with swipes and arrow keys', () => {
    render(<LibraryScroll library={library} onClose={() => undefined} />);
    const sheet = screen.getByRole('dialog', { name: 'Library' });
    fireEvent.touchStart(sheet, { touches: [{ clientX: 300 }] });
    fireEvent.touchEnd(sheet, { changedTouches: [{ clientX: 100 }] });
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    fireEvent.keyDown(sheet, { key: 'ArrowRight' });
    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
    fireEvent.touchStart(sheet, { touches: [{ clientX: 100 }] });
    fireEvent.touchEnd(sheet, { changedTouches: [{ clientX: 300 }] });
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    fireEvent.keyDown(sheet, { key: 'ArrowLeft' });
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('a tiny drag does not turn the page; Close and Escape call onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<LibraryScroll library={library} onClose={onClose} />);
    const sheet = screen.getByRole('dialog', { name: 'Library' });
    fireEvent.touchStart(sheet, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(sheet, { changedTouches: [{ clientX: 180 }] });
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    await user.click(within(sheet).getByRole('button', { name: 'Close Library' }));
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('with no documents there is one page and a note', () => {
    render(<LibraryScroll library={{ ...library, documents: [] }} onClose={() => undefined} />);
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(screen.getByText('No documents yet.')).toBeInTheDocument();
  });
});
