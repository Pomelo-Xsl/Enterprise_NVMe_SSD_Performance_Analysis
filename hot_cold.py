"""Window-based hot/cold page classification for SSD cache simulations.

The classifier models a controller that periodically promotes frequently
accessed logical pages into a hot tier and ages inactive pages back to a cold
tier.  It is intentionally deterministic so simulations are reproducible.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Iterable

from models import IOSample


@dataclass(frozen=True)
class PageHeat:
    """Snapshot of one page's heat classification."""

    page: int
    accesses: int
    reads: int
    writes: int
    score: float
    tier: str
    last_access_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HeatTransition:
    """A page promotion or demotion event."""

    timestamp_ms: int
    page: int
    previous_tier: str
    current_tier: str
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


class HotColdClassifier:
    """Classify pages from accesses within a sliding time window.

    Reads and writes can be assigned different weights.  A page is promoted
    after its weighted access score reaches ``hot_threshold`` and demoted when
    its score falls below ``cold_threshold``.  Separate thresholds provide
    hysteresis and prevent rapid hot/cold oscillation.
    """

    def __init__(
        self,
        window_ms: int = 10_000,
        hot_threshold: float = 4.0,
        cold_threshold: float = 2.0,
        read_weight: float = 1.0,
        write_weight: float = 1.5,
    ) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        if cold_threshold < 0 or hot_threshold <= cold_threshold:
            raise ValueError("hot_threshold must exceed cold_threshold")
        if read_weight <= 0 or write_weight <= 0:
            raise ValueError("access weights must be positive")

        self.window_ms = window_ms
        self.hot_threshold = hot_threshold
        self.cold_threshold = cold_threshold
        self.read_weight = read_weight
        self.write_weight = write_weight
        self._events: dict[int, deque[tuple[int, str]]] = defaultdict(deque)
        self._tiers: dict[int, str] = {}
        self._last_access: dict[int, int] = {}
        self.transitions: list[HeatTransition] = []

    def _prune(self, page: int, timestamp_ms: int) -> None:
        cutoff = timestamp_ms - self.window_ms
        events = self._events[page]
        while events and events[0][0] < cutoff:
            events.popleft()

    def _score(self, page: int) -> tuple[float, int, int]:
        reads = 0
        writes = 0
        for _, operation in self._events[page]:
            if operation.startswith("r"):
                reads += 1
            else:
                writes += 1
        score = reads * self.read_weight + writes * self.write_weight
        return score, reads, writes

    def observe(self, sample: IOSample) -> PageHeat:
        operation = sample.operation.lower()
        if not (operation.startswith("r") or operation.startswith("w")):
            raise ValueError(f"unsupported operation: {sample.operation}")

        page = sample.lba
        self._prune(page, sample.timestamp_ms)
        self._events[page].append((sample.timestamp_ms, operation))
        self._last_access[page] = sample.timestamp_ms

        previous = self._tiers.get(page, "cold")
        score, reads, writes = self._score(page)
        current = previous
        if previous == "cold" and score >= self.hot_threshold:
            current = "hot"
        elif previous == "hot" and score < self.cold_threshold:
            current = "cold"

        self._tiers[page] = current
        if current != previous:
            self.transitions.append(
                HeatTransition(
                    timestamp_ms=sample.timestamp_ms,
                    page=page,
                    previous_tier=previous,
                    current_tier=current,
                    score=score,
                )
            )

        return PageHeat(
            page=page,
            accesses=reads + writes,
            reads=reads,
            writes=writes,
            score=score,
            tier=current,
            last_access_ms=sample.timestamp_ms,
        )

    def classify(self, page: int, timestamp_ms: int | None = None) -> PageHeat:
        if timestamp_ms is not None:
            self._prune(page, timestamp_ms)
        score, reads, writes = self._score(page)
        tier = self._tiers.get(page, "cold")
        if tier == "hot" and score < self.cold_threshold:
            tier = "cold"
        return PageHeat(
            page=page,
            accesses=reads + writes,
            reads=reads,
            writes=writes,
            score=score,
            tier=tier,
            last_access_ms=self._last_access.get(page, 0),
        )

    def snapshot(self, timestamp_ms: int | None = None) -> list[PageHeat]:
        pages = set(self._events) | set(self._tiers)
        snapshots = [self.classify(page, timestamp_ms) for page in pages]
        return sorted(snapshots, key=lambda item: (-item.score, item.page))

    def summary(self, timestamp_ms: int | None = None) -> dict:
        snapshots = self.snapshot(timestamp_ms)
        tier_counts = Counter(item.tier for item in snapshots)
        return {
            "page_count": len(snapshots),
            "hot_pages": tier_counts.get("hot", 0),
            "cold_pages": tier_counts.get("cold", 0),
            "promotions": sum(item.current_tier == "hot" for item in self.transitions),
            "demotions": sum(item.current_tier == "cold" for item in self.transitions),
            "pages": [item.to_dict() for item in snapshots],
            "transitions": [item.to_dict() for item in self.transitions],
        }


def classify_workload(
    samples: Iterable[IOSample],
    **classifier_options,
) -> dict:
    """Classify a complete workload and return its final heat summary."""

    classifier = HotColdClassifier(**classifier_options)
    last_timestamp = 0
    for sample in samples:
        classifier.observe(sample)
        last_timestamp = sample.timestamp_ms
    return classifier.summary(last_timestamp)
