export interface MatchItem {
  match_id: string;
  league: string;
  league_name: string;
  kickoff_iso: string;
  home_team: string;
  away_team: string;
  home_country: string;
  away_country: string;
  btts: {
    label: 'YES' | 'NO';
    confidence: number;
    market_yes: number | null;
    xg_yes: number | null;
    availability: 'full' | 'partial';
  };
  elo?: { home: number; away: number };
  odds?: { home: number; draw: number; away: number };
  // forward-compatible placeholder for GetStream.
  activity_id?: string;
  timestamp?: string;
  score?: string;
}

export interface FeedResponse {
  items: MatchItem[];
  next_page: number | null;
  has_more: boolean;
}

const API_BASE = '';

const sortMatches = (items: MatchItem[]): MatchItem[] => {
  return items
    .slice()
    .sort((a, b) => {
      const kickoffDiff = new Date(a.kickoff_iso).getTime() - new Date(b.kickoff_iso).getTime();
      if (kickoffDiff !== 0) return kickoffDiff;
      return b.btts.confidence - a.btts.confidence;
    });
};

export const fetchFeed = async (
  league: string,
  page: number,
  limit: number
): Promise<FeedResponse> => {
  const url = `${API_BASE}/feed?league=${league}&page=${page}&limit=${limit}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Feed response not ok');
    }
    const data = (await response.json()) as FeedResponse;
    return { ...data, items: sortMatches(data.items) };
  } catch (error) {
    const fallbackUrl = `${API_BASE}/upcoming?league=${league}`;
    const fallbackResponse = await fetch(fallbackUrl);
    if (!fallbackResponse.ok) {
      throw error instanceof Error ? error : new Error('Unable to load feed');
    }
    const fallbackItems = (await fallbackResponse.json()) as MatchItem[];
    const items = sortMatches(fallbackItems).slice((page - 1) * limit, page * limit);
    return {
      items,
      next_page: items.length === limit ? page + 1 : null,
      has_more: items.length === limit,
    };
  }
};

export const fetcher = {
  fetchFeed,
};

// Future v2: integrate GetStream social reactions.
export const useStreamFeed = () => {
  // TODO: Implement GetStream feed subscription in v2.
  return {
    activities: [] as unknown[],
    status: 'idle' as 'idle' | 'loading' | 'error',
  };
};
