import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from './Toast';
import { useToast } from './useToast';

function Trigger(): React.JSX.Element {
  const { show } = useToast();
  return (
    <button type="button" onClick={() => show()}>
      go
    </button>
  );
}

const text = 'Not available in this demo.';

function setup(): void {
  render(
    <ToastProvider>
      <Trigger />
    </ToastProvider>,
  );
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the exact text', () => {
    setup();
    fireEvent.click(screen.getByText('go'));
    expect(screen.getByRole('status')).toHaveTextContent(text);
  });

  it('disappears after 3000 ms', () => {
    setup();
    fireEvent.click(screen.getByText('go'));
    act(() => void vi.advanceTimersByTime(2999));
    expect(screen.queryByText(text)).not.toBeNull();
    act(() => void vi.advanceTimersByTime(1));
    expect(screen.queryByText(text)).toBeNull();
  });

  it('dismisses on tap', () => {
    setup();
    fireEvent.click(screen.getByText('go'));
    fireEvent.click(screen.getByText(text));
    expect(screen.queryByText(text)).toBeNull();
  });

  it('replaces and restarts the timer on a second show', () => {
    setup();
    fireEvent.click(screen.getByText('go'));
    act(() => void vi.advanceTimersByTime(2000));
    fireEvent.click(screen.getByText('go'));
    expect(screen.getAllByText(text)).toHaveLength(1);
    act(() => void vi.advanceTimersByTime(2900));
    expect(screen.queryByText(text)).not.toBeNull();
    act(() => void vi.advanceTimersByTime(100));
    expect(screen.queryByText(text)).toBeNull();
  });

  it('keeps a single persistent status region', () => {
    setup();
    expect(screen.getAllByRole('status')).toHaveLength(1);
    fireEvent.click(screen.getByText('go'));
    fireEvent.click(screen.getByText('go'));
    expect(screen.getAllByRole('status')).toHaveLength(1);
  });
});
