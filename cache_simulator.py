"""In-memory cache-policy models used for side-by-side analysis.

LRU-2 and ARC follow their usual recency/frequency ideas. The LIRS class is a
practical approximation suited to recorded IO traces rather than a controller
implementation. Every policy consumes the same materialized workload so the
comparison is repeatable.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict, deque
from typing import Deque, Iterable

from models import CacheState, IOSample


class _CachePolicy:
    """Shared counters and event recording; policy state stays in subclasses."""

    def __init__(self, capacity_pages: int, hot_window_ms: int = 1000):
        if capacity_pages < 1:
            raise ValueError("capacity_pages must be positive")
        self.state = CacheState(capacity_pages)
        self.hot_window_ms = hot_window_ms
        self.dirty_pages: set[int] = set()
        self.last_access: dict[int, int] = {}
        self.history: dict[int, Deque[int]] = defaultdict(deque)

    def is_hot(self, page: int, timestamp_ms: int) -> bool:
        history = self.history[page]
        return len(history) >= 2 and timestamp_ms - history[-2] <= self.hot_window_ms

    def record(
        self,
        sample: IOSample,
        hit: bool,
        evicted: int | None = None,
    ) -> dict:
        """Update hit, heat and dirty-page counters after one lookup."""
        hot = self.is_hot(sample.lba, sample.timestamp_ms)
        access_history = self.history[sample.lba]
        access_history.append(sample.timestamp_ms)
        if len(access_history) > 4:
            access_history.popleft()

        self.last_access[sample.lba] = sample.timestamp_ms
        if hit:
            self.state.hits += 1
            self.state.hot_hits += int(hot)
            self.state.cold_hits += int(not hot)
        else:
            self.state.misses += 1
        if sample.operation == "write":
            self.dirty_pages.add(sample.lba)

        dirty_eviction = evicted in self.dirty_pages if evicted is not None else False
        if evicted is not None:
            self.dirty_pages.discard(evicted)
            self.state.dirty_evictions += int(dirty_eviction)
            self.state.clean_evictions += int(not dirty_eviction)

        self.state.resident_pages = self.resident_count()
        self.state.dirty_pages = len(self.dirty_pages)
        return {
            "page": sample.lba,
            "hit": hit,
            "hot": hot,
            "evicted": evicted,
            "dirty_eviction": dirty_eviction,
        }

    def resident_count(self) -> int:
        raise NotImplementedError

    def access(self, sample: IOSample) -> dict:
        raise NotImplementedError

    def run(self, samples: Iterable[IOSample]) -> dict:
        events = [self.access(sample) for sample in samples]
        return {
            "algorithm": type(self).__name__,
            "state": self.state.to_dict(),
            "events": events,
        }


class LRU2Cache(_CachePolicy):
    """LRU-K with K=2; eviction favours pages with fewer than two references."""

    def __init__(self, capacity_pages: int, **kwargs):
        super().__init__(capacity_pages, **kwargs)
        self.pages: set[int] = set()
        self.references: dict[int, Deque[int]] = defaultdict(deque)

    def resident_count(self) -> int:
        return len(self.pages)

    def access(self, sample: IOSample) -> dict:
        page = sample.lba
        hit = page in self.pages
        evicted = None
        if not hit:
            if len(self.pages) >= self.state.capacity_pages:
                candidates = sorted(
                    self.pages,
                    key=lambda candidate: (
                        len(self.references[candidate]) >= 2,
                        (
                            self.references[candidate][0]
                            if self.references[candidate]
                            else -1
                        ),
                    ),
                )
                evicted = candidates[0]
                self.pages.remove(evicted)
            self.pages.add(page)

        references = self.references[page]
        references.append(sample.timestamp_ms)
        if len(references) > 2:
            references.popleft()
        return self.record(sample, hit, evicted)


class ARCCache(_CachePolicy):
    """Adaptive Replacement Cache with recency/frequency resident and ghost lists."""

    def __init__(self, capacity_pages: int, **kwargs):
        super().__init__(capacity_pages, **kwargs)
        self.t1 = OrderedDict()
        self.t2 = OrderedDict()
        self.b1 = OrderedDict()
        self.b2 = OrderedDict()
        self.p = 0

    def resident_count(self) -> int:
        return len(self.t1) + len(self.t2)

    def _replace(self, incoming_page: int) -> int:
        if self.t1 and (
            len(self.t1) > self.p
            or (incoming_page in self.b2 and len(self.t1) == self.p)
        ):
            victim, _ = self.t1.popitem(last=False)
            self.b1[victim] = None
            return victim
        victim, _ = self.t2.popitem(last=False)
        self.b2[victim] = None
        return victim

    def access(self, sample: IOSample) -> dict:
        page = sample.lba
        evicted = None
        if page in self.t1 or page in self.t2:
            self.t1.pop(page, None)
            self.t2.pop(page, None)
            self.t2[page] = None
            return self.record(sample, True)
        if page in self.b1:
            self.p = min(
                self.state.capacity_pages,
                self.p + max(1, len(self.b2) // max(1, len(self.b1))),
            )
            evicted = self._replace(page)
            self.b1.pop(page)
            self.t2[page] = None
        elif page in self.b2:
            self.p = max(0, self.p - max(1, len(self.b1) // max(1, len(self.b2))))
            evicted = self._replace(page)
            self.b2.pop(page)
            self.t2[page] = None
        else:
            if self.resident_count() >= self.state.capacity_pages:
                evicted = self._replace(page)
            self.t1[page] = None
        while len(self.b1) > self.state.capacity_pages:
            self.b1.popitem(last=False)
        while len(self.b2) > self.state.capacity_pages:
            self.b2.popitem(last=False)
        return self.record(sample, False, evicted)


class LIRSCache(_CachePolicy):
    """Practical LIRS approximation: low inter-reference reuse stays resident."""

    def __init__(self, capacity_pages: int, **kwargs):
        super().__init__(capacity_pages, **kwargs)
        self.stack = OrderedDict()
        self.hir = OrderedDict()
        self.lir = set()
        self.lir_limit = max(1, capacity_pages - 1)

    def resident_count(self) -> int:
        return len(self.lir) + len(self.hir)

    def access(self, sample: IOSample) -> dict:
        page = sample.lba
        hit = page in self.lir or page in self.hir
        evicted = None
        self.stack.pop(page, None)
        self.stack[page] = None
        if page in self.lir:
            return self.record(sample, True)
        if page in self.hir:
            self.hir.pop(page)
            self.lir.add(page)
            if len(self.lir) > self.lir_limit:
                demote = next(iter(self.lir - {page}))
                self.lir.remove(demote)
                self.hir[demote] = None
            return self.record(sample, True)
        if self.resident_count() >= self.state.capacity_pages:
            evicted, _ = (
                self.hir.popitem(last=False)
                if self.hir
                else (next(iter(self.lir)), None)
            )
            self.lir.discard(evicted)
        if len(self.lir) < self.lir_limit:
            self.lir.add(page)
        else:
            self.hir[page] = None
        return self.record(sample, False, evicted)


def compare_algorithms(samples: Iterable[IOSample], capacity_pages: int) -> dict:
    """Run every policy against an identical materialized access stream."""
    workload = list(samples)
    algorithms = {
        "lru2": LRU2Cache,
        "arc": ARCCache,
        "lirs": LIRSCache,
    }
    return {
        name: cache_class(capacity_pages).run(workload)
        for name, cache_class in algorithms.items()
    }
