'use client';

import { useState } from 'react';
import { apiMore } from '@/lib/api';

// LoadMore
// Props: { searchId: string; hasMore: boolean; busy?: boolean;
//          onMore(newResults: Result[], hasMore: boolean): void;
//          onError?(msg: string): void }
//
// Hidden/disabled when !hasMore. Calls apiMore(searchId) which fetches the next
// page from each non-exhausted provider, re-ranks, and returns only the newly
// added results. The parent appends them and updates hasMore.

export default function LoadMore({ searchId, hasMore, busy, onMore, onError }) {
  const [loading, setLoading] = useState(false);

  if (!hasMore) return null;

  const handleClick = async () => {
    if (loading || busy) return;
    setLoading(true);
    try {
      const res = await apiMore(searchId);
      onMore?.(res?.results || [], Boolean(res?.has_more));
    } catch (err) {
      onError?.(err?.message || 'Could not load more results.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="omni-loadmore">
      <button
        type="button"
        className="omni-btn omni-btn--secondary"
        onClick={handleClick}
        disabled={loading || busy}
      >
        {loading ? 'Loading…' : 'Load more results'}
      </button>
    </div>
  );
}
