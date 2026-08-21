"""Deterministic SSD-cache replacement simulators: LRU-2, ARC and LIRS-inspired."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Deque, Iterable, Optional

from models import CacheState, IOSample


@dataclass
class AccessResult:
    """Outcome of one cache lookup, including write-back side effects."""

    page: int
    hit: bool
    hot: bool
    evicted: Optional[int] = None
    dirty_eviction: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class BaseCache(ABC):
    """Common accounting shared by every replacement policy."""

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
        evicted: Optional[int] = None,
    ) -> AccessResult:
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
        return AccessResult(sample.lba, hit, hot, evicted, dirty_eviction)

    @abstractmethod
    def resident_count(self) -> int:
        """Return the number of pages currently backed by cache capacity."""

    @abstractmethod
    def access(self, sample: IOSample) -> AccessResult:
        """Process one access according to the concrete replacement policy."""

    def run(self, samples: Iterable[IOSample]) -> dict:
        events = [self.access(sample) for sample in samples]
        return {
            "algorithm": type(self).__name__,
            "state": self.state.to_dict(),
            "events": [event.to_dict() for event in events],
        }


class LRU2Cache(BaseCache):
    """LRU-K with K=2; eviction favours pages with fewer than two references."""

    def __init__(self, capacity_pages: int, **kwargs):
        super().__init__(capacity_pages, **kwargs)
        self.pages: set[int] = set()
        self.references: dict[int, Deque[int]] = defaultdict(deque)

    def resident_count(self) -> int:
        return len(self.pages)

    def access(self, sample: IOSample) -> AccessResult:
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


class ARCCache(BaseCache):
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

    def access(self, sample: IOSample) -> AccessResult:
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


class LIRSCache(BaseCache):
    """Practical LIRS approximation: low inter-reference reuse stays resident."""

    def __init__(self, capacity_pages: int, **kwargs):
        super().__init__(capacity_pages, **kwargs)
        self.stack = OrderedDict()
        self.hir = OrderedDict()
        self.lir = set()
        self.lir_limit = max(1, capacity_pages - 1)

    def resident_count(self) -> int:
        return len(self.lir) + len(self.hir)

    def access(self, sample: IOSample) -> AccessResult:
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
