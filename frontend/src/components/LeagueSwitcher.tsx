import { useEffect, useRef } from 'react';

interface LeagueSwitcherProps {
  activeLeague: string;
  leagues: readonly string[];
  onLeagueChange: (league: string) => void;
}

export const LeagueSwitcher = ({ activeLeague, leagues, onLeagueChange }: LeagueSwitcherProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const activeButton = container.querySelector<HTMLButtonElement>(`[data-league="${activeLeague}"]`);
    if (activeButton) {
      activeButton.scrollIntoView({ inline: 'center', behavior: 'smooth', block: 'nearest' });
    }
  }, [activeLeague]);

  return (
    <div
      ref={containerRef}
      className="flex items-center gap-2 overflow-x-auto rounded-full border border-border bg-card p-1 text-sm shadow-inner"
    >
      {leagues.map((code) => {
        const isActive = code === activeLeague;
        return (
          <button
            key={code}
            data-league={code}
            type="button"
            onClick={() => onLeagueChange(code)}
            className={`whitespace-nowrap rounded-full px-4 py-1 font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
              isActive ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
          >
            {code}
          </button>
        );
      })}
    </div>
  );
};
