import { useMemo, useState } from 'react';
import type { MatchItem } from '../api/client';
import { Modal } from './Modal';

const toPolarityPercent = (label: 'YES' | 'NO', probYes: number | null): number | null => {
  if (probYes == null) return null;
  const percent = label === 'YES' ? probYes * 100 : (1 - probYes) * 100;
  return Math.round(percent * 10) / 10;
};

const getConfidencePercent = (match: MatchItem): number => {
  if (typeof match.btts.confidence === 'number' && !Number.isNaN(match.btts.confidence)) {
    return Math.round(match.btts.confidence * 1000) / 10;
  }
  const derivedSources = [match.btts.market_yes, match.btts.xg_yes]
    .map((value) => toPolarityPercent(match.btts.label, value))
    .filter((value): value is number => value != null);
  if (derivedSources.length === 0) return 0;
  const average = derivedSources.reduce((acc, value) => acc + value, 0) / derivedSources.length;
  return Math.round(average * 10) / 10;
};

const getInitials = (name: string) =>
  name
    .split(' ')
    .map((piece) => piece[0])
    .join('')
    .slice(0, 3)
    .toUpperCase();

const dateFormatter = new Intl.DateTimeFormat([], {
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  month: 'short',
  day: '2-digit',
});

interface MatchCardProps {
  match: MatchItem;
}

export const MatchCard = ({ match }: MatchCardProps) => {
  const [isModalOpen, setModalOpen] = useState(false);
  const confidence = useMemo(() => getConfidencePercent(match), [match]);
  const marketPercent = useMemo(() => toPolarityPercent(match.btts.label, match.btts.market_yes), [match]);
  const xgPercent = useMemo(() => toPolarityPercent(match.btts.label, match.btts.xg_yes), [match]);
  const kickoff = useMemo(() => dateFormatter.format(new Date(match.kickoff_iso)), [match.kickoff_iso]);

  const polarityColor = match.btts.label === 'YES' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-muted text-foreground';

  return (
    <article className="relative overflow-hidden rounded-3xl border border-border bg-card p-6 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <span className="text-xs uppercase tracking-wide text-muted-foreground">{match.league_name}</span>
          <h2 className="mt-2 text-xl font-semibold">
            {match.home_team} vs {match.away_team}
          </h2>
          <p className="text-sm text-muted-foreground">{kickoff}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex flex-col items-center gap-2">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/5 text-lg font-bold text-primary">
                {getInitials(match.home_team)}
              </span>
              <span className="text-sm text-muted-foreground">vs</span>
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/5 text-lg font-bold text-primary">
                {getInitials(match.away_team)}
              </span>
            </div>
            {match.btts.availability === 'partial' && (
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="flex items-center gap-2 rounded-full bg-amber-500/20 px-3 py-1 text-xs font-medium text-amber-700 shadow-sm"
              >
                Partial Data
              </button>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${polarityColor}`}>
              BTTS: {match.btts.label}
            </span>
            <span className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow">
              {confidence.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl bg-muted/40 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Market</h3>
          <p className="text-lg font-semibold">
            {marketPercent != null ? `${marketPercent.toFixed(1)}%` : 'n/a'}
          </p>
          <p className="text-xs text-muted-foreground">Aligned to {match.btts.label}</p>
        </div>
        <div className="rounded-2xl bg-muted/40 p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">xG Model</h3>
          <p className="text-lg font-semibold">{xgPercent != null ? `${xgPercent.toFixed(1)}%` : 'n/a'}</p>
          <p className="text-xs text-muted-foreground">Aligned to {match.btts.label}</p>
        </div>
        <div className="rounded-2xl bg-muted/40 p-4 space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Odds</h3>
          {match.odds ? (
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Home</dt>
                <dd className="font-semibold">{match.odds.home.toFixed(2)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Draw</dt>
                <dd className="font-semibold">{match.odds.draw.toFixed(2)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Away</dt>
                <dd className="font-semibold">{match.odds.away.toFixed(2)}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">Odds coming soon.</p>
          )}
        </div>
      </div>

      <Modal
        isOpen={isModalOpen}
        title="Cup fallback"
        description="Using domestic stats while cup-level data is partial."
        onClose={() => setModalOpen(false)}
      />
    </article>
  );
};

export { toPolarityPercent };

