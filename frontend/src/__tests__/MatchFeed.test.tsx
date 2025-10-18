import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import React from 'react';
import { MatchFeed } from '../components/MatchFeed';
import { toPolarityPercent } from '../components/MatchCard';
import { usePreferredColorScheme } from '../hooks/usePreferredColorScheme';

vi.mock('../hooks/useInfiniteFeed');

const mockFetchNextPage = vi.fn();
const mockRemove = vi.fn();
const mockRefetch = vi.fn(() => Promise.resolve());

const mockUseInfiniteFeed = vi.mocked(require('../hooks/useInfiniteFeed').useInfiniteFeed);

const baseMatch = {
  match_id: 'PL-1',
  league: 'PL',
  league_name: 'Premier League',
  kickoff_iso: '2025-05-03T12:00:00Z',
  home_team: 'Arsenal',
  away_team: 'Chelsea',
  home_country: 'England',
  away_country: 'England',
  btts: {
    label: 'NO' as const,
    confidence: 0.52,
    market_yes: 0.44,
    xg_yes: 0.4,
    availability: 'partial' as const,
  },
  odds: { home: 2.2, draw: 3.1, away: 3.4 },
};

const setupMock = (overrides: Record<string, unknown> = {}) => {
  mockUseInfiniteFeed.mockReturnValue({
    entries: [baseMatch],
    query: {
      hasNextPage: true,
      isFetchingNextPage: false,
      isFetching: false,
      isLoading: false,
      fetchNextPage: mockFetchNextPage,
      remove: mockRemove,
      refetch: mockRefetch,
      data: { pages: [{ items: [baseMatch], next_page: 2, has_more: true }] },
      ...overrides,
    },
  });
};

class MockIntersectionObserver {
  constructor(private readonly callback: IntersectionObserverCallback) {
    MockIntersectionObserver.instances.push(this);
    this.callback = callback;
  }
  static instances: MockIntersectionObserver[] = [];
  observe() {}
  disconnect() {}
  trigger(entries: IntersectionObserverEntry[]) {
    this.callback(entries, this as unknown as IntersectionObserver);
  }
}

declare global {
  interface Window {
    IntersectionObserver: typeof MockIntersectionObserver;
  }
}

beforeEach(() => {
  MockIntersectionObserver.instances = [];
  // @ts-expect-error - override for tests
  window.IntersectionObserver = MockIntersectionObserver;
  setupMock();
  mockFetchNextPage.mockReset();
  mockRemove.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('MatchFeed', () => {
  it('loads the next page when the sentinel enters the viewport', () => {
    render(<MatchFeed league="PL" />);
    const observer = MockIntersectionObserver.instances[0];
    act(() => {
      observer.trigger([
        {
          isIntersecting: true,
        } as IntersectionObserverEntry,
      ]);
    });
    expect(mockFetchNextPage).toHaveBeenCalled();
  });

  it('removes existing data when the league changes', () => {
    const { rerender } = render(<MatchFeed league="PL" />);
    rerender(<MatchFeed league="SA" />);
    expect(mockRemove).toHaveBeenCalledTimes(1);
  });
});

describe('MatchCard polarity', () => {
  it('computes market polarity for YES', () => {
    expect(toPolarityPercent('YES', 0.42)).toBeCloseTo(42);
  });

  it('computes market polarity for NO', () => {
    expect(toPolarityPercent('NO', 0.42)).toBeCloseTo(58);
  });
});

describe('MatchCard partial data tag', () => {
  it('renders partial data indicator', () => {
    render(<MatchFeed league="PL" />);
    expect(screen.getByText(/Partial Data/i)).toBeInTheDocument();
  });
});

describe('usePreferredColorScheme', () => {
  it('persists dark mode preference', () => {
    const listeners: Record<string, (event: MediaQueryListEvent) => void> = {};
    const addEventListener = vi.fn((event: string, handler: (event: MediaQueryListEvent) => void) => {
      listeners[event] = handler;
    });

    const removeEventListener = vi.fn();
    // @ts-expect-error - partial implementation for tests
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: true,
      addEventListener,
      removeEventListener,
    }));
    const setItemSpy = vi.spyOn(window.localStorage.__proto__, 'setItem');

    const TestComponent = () => {
      const [isDark, toggle] = usePreferredColorScheme();
      return (
        <button type="button" onClick={toggle}>
          {isDark ? 'dark' : 'light'}
        </button>
      );
    };

    render(<TestComponent />);
    const button = screen.getByRole('button');
    expect(button.textContent).toBe('dark');
    act(() => {
      button.click();
    });
    expect(setItemSpy).toHaveBeenCalledWith('tef:theme', 'light');
  });
});
