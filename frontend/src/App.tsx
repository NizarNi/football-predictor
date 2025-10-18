import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { MatchFeed } from './components/MatchFeed';
import { LeagueSwitcher } from './components/LeagueSwitcher';
import { usePreferredColorScheme } from './hooks/usePreferredColorScheme';

const LEAGUES = ['PL', 'SA', 'LL', 'BL1', 'FL1', 'UCL', 'UEL'] as const;
type LeagueCode = (typeof LEAGUES)[number];

const Layout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const resolveInitialLeague = (): LeagueCode => {
    const params = new URLSearchParams(location.search);
    const fromUrl = params.get('league');
    if (fromUrl && LEAGUES.includes(fromUrl as LeagueCode)) {
      return fromUrl as LeagueCode;
    }
    const stored = typeof window !== 'undefined' ? localStorage.getItem('tef:lastLeague') : null;
    if (stored && LEAGUES.includes(stored as LeagueCode)) {
      return stored as LeagueCode;
    }
    return 'PL';
  };

  const [league, setLeague] = useState<LeagueCode>(resolveInitialLeague);
  const [isDark, toggleTheme] = usePreferredColorScheme();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
  }, [isDark]);

  useEffect(() => {
    const nextParams = new URLSearchParams(location.search);
    nextParams.set('league', league);
    navigate({ search: nextParams.toString() }, { replace: true });
    localStorage.setItem('tef:lastLeague', league);
  }, [league, location.search, navigate]);

  return (
    <div className="min-h-screen bg-surface text-foreground transition-colors duration-300">
      <header className="sticky top-0 z-40 bg-surface/95 backdrop-blur shadow-sm">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold sm:text-3xl">Top European Football</h1>
            <p className="text-sm text-muted-foreground">
              Deterministic BTTS confidence across Europe&apos;s elite competitions.
            </p>
          </div>
          <div className="flex w-full flex-col items-stretch gap-3 sm:w-auto sm:flex-row sm:items-center">
            <LeagueSwitcher
              activeLeague={league}
              leagues={LEAGUES}
              onLeagueChange={(code) => setLeague(code)}
            />
            <div className="flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 shadow-sm">
              <span className="text-sm text-muted-foreground">Search</span>
              <input
                type="text"
                placeholder="Coming soon"
                className="w-28 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                disabled
              />
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              className="rounded-full border border-border bg-card px-4 py-2 text-sm shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
            >
              {isDark ? 'Light' : 'Dark'} mode
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto min-h-[calc(100vh-6rem)] max-w-6xl px-4 pb-12 pt-6">
        <MatchFeed league={league} />
      </main>
    </div>
  );
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000 * 30,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Outlet />} />
        </Route>
      </Routes>
    </QueryClientProvider>
  );
}
