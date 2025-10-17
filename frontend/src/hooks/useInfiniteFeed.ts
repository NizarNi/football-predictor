import { useEffect, useMemo, useRef } from 'react';
import { useInfiniteQuery, UseInfiniteQueryResult } from '@tanstack/react-query';
import { fetchFeed, MatchItem } from '../api/client';

const PAGE_SIZE = 10;

export interface UseInfiniteFeedOptions {
  league: string;
}

export const useInfiniteFeed = ({ league }: UseInfiniteFeedOptions) => {
  const query = useInfiniteQuery<{ items: MatchItem[]; next_page: number | null; has_more: boolean }, Error>({
    queryKey: ['feed', league],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => fetchFeed(league, pageParam, PAGE_SIZE),
    getNextPageParam: (lastPage) => lastPage.next_page ?? undefined,
  });

  const { data, hasNextPage, isFetchingNextPage, fetchNextPage } = query;

  const entries = useMemo(() => data?.pages.flatMap((page) => page.items) ?? [], [data]);

  const prefetchTriggered = useRef(false);
  useEffect(() => {
    if (!data || !hasNextPage || isFetchingNextPage) {
      prefetchTriggered.current = false;
      return;
    }
    const totalPages = data.pages.length;
    const loadedItems = entries.length;
    const totalCapacity = totalPages * PAGE_SIZE;
    const ratio = loadedItems / totalCapacity;
    if (ratio >= 0.75 && !prefetchTriggered.current) {
      prefetchTriggered.current = true;
      fetchNextPage();
    }
  }, [data, entries.length, fetchNextPage, hasNextPage, isFetchingNextPage]);

  return {
    query: query as UseInfiniteQueryResult<{ items: MatchItem[]; next_page: number | null; has_more: boolean }, Error>,
    entries,
  };
};
