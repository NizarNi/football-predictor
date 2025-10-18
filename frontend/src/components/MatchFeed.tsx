import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TouchEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useInfiniteFeed } from '../hooks/useInfiniteFeed';
import { MatchCard } from './MatchCard';
import type { MatchItem } from '../api/client';

interface MatchFeedProps {
  league: string;
}

const SKELETON_COUNT = 3;

const SkeletonCard = () => (
  <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
    <div className="h-4 w-32 animate-pulse rounded-full bg-muted" />
    <div className="mt-4 h-6 w-48 animate-pulse rounded-full bg-muted" />
    <div className="mt-6 flex gap-4">
      <div className="h-10 w-20 animate-pulse rounded-2xl bg-muted" />
      <div className="h-10 w-20 animate-pulse rounded-2xl bg-muted" />
    </div>
  </div>
);

export const MatchFeed = ({ league }: MatchFeedProps) => {
  const { entries, query } = useInfiniteFeed({ league });
  const { remove, fetchNextPage, hasNextPage, isFetchingNextPage, refetch, isFetching, isLoading } = query;
  const observerRef = useRef<IntersectionObserver>();
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    remove();
  }, [league, remove]);

  useEffect(() => {
    if (!sentinelRef.current) return;
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    observerRef.current = new IntersectionObserver((entriesList) => {
      entriesList.forEach((entry) => {
        if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      });
    });
    observerRef.current.observe(sentinelRef.current);
    return () => observerRef.current?.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  const handleTouchStart = useCallback((event: TouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 1) return;
    startY.current = event.touches[0].clientY;
  }, []);

  const handleTouchMove = useCallback(
    (event: TouchEvent<HTMLDivElement>) => {
      if (startY.current === null) return;
      const delta = event.touches[0].clientY - startY.current;
      if (delta > 90 && !isRefreshing && window.scrollY === 0) {
        setIsRefreshing(true);
        refetch().finally(() => setIsRefreshing(false));
      }
    },
    [isRefreshing, refetch]
  );

  const renderEntries = useMemo(
    () =>
      entries.map((match: MatchItem) => (
        <motion.li
          layout
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.3 }}
          key={`${match.match_id}`}
        >
          <MatchCard match={match} />
        </motion.li>
      )),
    [entries]
  );

  const isEmpty = !isLoading && entries.length === 0;

  return (
    <div
      className="relative space-y-4"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
    >
      {isRefreshing && (
        <div className="sticky top-24 z-30 mx-auto w-fit rounded-full bg-primary/10 px-4 py-1 text-xs text-primary shadow-sm">
          Refreshing…
        </div>
      )}
      {isEmpty && (
        <div className="rounded-3xl border border-dashed border-border bg-card/60 p-12 text-center text-muted-foreground">
          No matches scheduled yet. Check back soon.
        </div>
      )}
      <ul className="flex flex-col gap-4">
        <AnimatePresence>{renderEntries}</AnimatePresence>
      </ul>
      {(isFetching || isFetchingNextPage) && (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: SKELETON_COUNT }).map((_, index) => (
            <SkeletonCard key={index} />
          ))}
        </div>
      )}
      <div ref={sentinelRef} className="h-1" />
    </div>
  );
};
