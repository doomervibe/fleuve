"""
Performance benchmarks for lazy validation, tiered caching, and pickle storage.

Run with:
    pytest fleuve/tests/test_perf.py -v -s

Each test prints a comparison table so regressions are easy to spot.
"""

import datetime
import json
import pickle
import time
from collections import OrderedDict
from typing import Literal
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, Field, TypeAdapter

from fleuve.model import EventBase, StateBase
from fleuve.repo import InProcessEuphemeralStorage, StoredState
from fleuve.stream import ConsumedEvent


# ---------------------------------------------------------------------------
# Heavyweight models that make deserialization cost noticeable
# ---------------------------------------------------------------------------

class PerfEvent(EventBase):
    type: Literal["perf_event"] = "perf_event"
    payload: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class PerfState(StateBase):
    counter: int = 0
    items: list[dict] = Field(default_factory=list)
    subscriptions: list = Field(default_factory=list)
    external_subscriptions: list = Field(default_factory=list)


def _make_event_dict(i: int, n_tags: int = 20, payload_keys: int = 30) -> dict:
    return {
        "type": "perf_event",
        "metadata_": {},
        "payload": {f"key_{k}": f"value_{k}_{i}" for k in range(payload_keys)},
        "tags": [f"tag_{t}" for t in range(n_tags)],
    }


def _make_stored_state(wf_id: str, n_items: int = 50) -> StoredState[PerfState]:
    state = PerfState(
        counter=42,
        items=[{"id": i, "name": f"item-{i}", "meta": {"x": i}} for i in range(n_items)],
    )
    return StoredState(id=wf_id, version=1, state=state)


_perf_adapter: TypeAdapter = TypeAdapter(PerfEvent)


def _validate_perf_event(raw: dict) -> PerfEvent:
    return _perf_adapter.validate_python(raw)


# ---------------------------------------------------------------------------
# 1. Lazy ConsumedEvent: skip validation vs eager validation
# ---------------------------------------------------------------------------

class TestLazyValidationPerf:
    """Measure how much time is saved when events are never accessed."""

    N = 5_000

    def _build_lazy_events(self):
        now = datetime.datetime.now()
        raw_bodies = [_make_event_dict(i) for i in range(self.N)]
        return [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=i,
                global_id=i,
                at=now,
                workflow_type="bench",
                event_type="perf_event",
                _raw_body=raw_bodies[i],
                _body_validator=_validate_perf_event,
            )
            for i in range(self.N)
        ]

    def _build_eager_events(self):
        now = datetime.datetime.now()
        raw_bodies = [_make_event_dict(i) for i in range(self.N)]
        return [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=i,
                global_id=i,
                at=now,
                workflow_type="bench",
                event_type="perf_event",
                event=_validate_perf_event(raw_bodies[i]),
            )
            for i in range(self.N)
        ]

    def test_lazy_skip_is_faster_than_eager(self):
        """Routing that never touches .event should be faster with lazy events.

        Pre-builds raw bodies so the timing isolates construction + routing
        from the dict-building overhead that both paths share.
        """
        now = datetime.datetime.now()
        raw_bodies = [_make_event_dict(i) for i in range(self.N)]

        # Eager: validate every body, then route by event_type
        t0 = time.perf_counter()
        for i in range(self.N):
            ev = ConsumedEvent(
                workflow_id=f"wf-{i}", event_no=i, global_id=i, at=now,
                workflow_type="bench", event_type="perf_event",
                event=_validate_perf_event(raw_bodies[i]),
            )
            _ = ev.event_type
        eager_ms = (time.perf_counter() - t0) * 1000

        # Lazy: skip validation, route by event_type string only
        t0 = time.perf_counter()
        for i in range(self.N):
            ev = ConsumedEvent(
                workflow_id=f"wf-{i}", event_no=i, global_id=i, at=now,
                workflow_type="bench", event_type="perf_event",
                _raw_body=raw_bodies[i], _body_validator=_validate_perf_event,
            )
            _ = ev.event_type
        lazy_ms = (time.perf_counter() - t0) * 1000

        speedup = eager_ms / lazy_ms if lazy_ms > 0 else float("inf")
        print(
            f"\n  Lazy skip vs Eager ({self.N} events):"
            f"\n    Eager (validate all) : {eager_ms:8.1f} ms"
            f"\n    Lazy  (skip .event)  : {lazy_ms:8.1f} ms"
            f"\n    Speedup             : {speedup:8.1f}x"
        )
        assert speedup > 1.5, f"Expected >1.5x speedup, got {speedup:.1f}x"

    def test_lazy_access_comparable_to_eager(self):
        """When all events ARE accessed, lazy should not be catastrophically slower.

        Some overhead from the property dispatch and isinstance guard is
        expected; the point is to confirm it stays within a small constant
        factor, not orders of magnitude.
        """
        now = datetime.datetime.now()
        raw_bodies = [_make_event_dict(i) for i in range(self.N)]

        # Eager: validate during construction, then access .event
        t0 = time.perf_counter()
        for i in range(self.N):
            ev = ConsumedEvent(
                workflow_id=f"wf-{i}", event_no=i, global_id=i, at=now,
                workflow_type="bench", event_type="perf_event",
                event=_validate_perf_event(raw_bodies[i]),
            )
            _ = ev.event
        eager_ms = (time.perf_counter() - t0) * 1000

        # Lazy: validate on first .event access
        t0 = time.perf_counter()
        for i in range(self.N):
            ev = ConsumedEvent(
                workflow_id=f"wf-{i}", event_no=i, global_id=i, at=now,
                workflow_type="bench", event_type="perf_event",
                _raw_body=raw_bodies[i], _body_validator=_validate_perf_event,
            )
            _ = ev.event
        lazy_ms = (time.perf_counter() - t0) * 1000

        ratio = lazy_ms / eager_ms if eager_ms > 0 else float("inf")
        print(
            f"\n  Lazy access vs Eager ({self.N} events):"
            f"\n    Eager : {eager_ms:8.1f} ms"
            f"\n    Lazy  : {lazy_ms:8.1f} ms"
            f"\n    Ratio : {ratio:8.2f}x  (1.0 = same speed)"
        )
        assert ratio < 3.0, f"Lazy-with-access should be < 3x slower, got {ratio:.2f}x"

    def test_partial_access_proportional(self):
        """Accessing 10% of events should be ~10x faster than 100%."""

        events = self._build_lazy_events()
        access_pct = 0.10
        access_count = int(self.N * access_pct)

        # Access all
        t0 = time.perf_counter()
        for ev in events:
            _ = ev.event
        all_ms = (time.perf_counter() - t0) * 1000

        # Rebuild and access only 10%
        events = self._build_lazy_events()
        t0 = time.perf_counter()
        for ev in events[:access_count]:
            _ = ev.event
        for ev in events[access_count:]:
            _ = ev.event_type
        partial_ms = (time.perf_counter() - t0) * 1000

        speedup = all_ms / partial_ms if partial_ms > 0 else float("inf")
        print(
            f"\n  Partial access ({access_pct:.0%} of {self.N}):"
            f"\n    100% access : {all_ms:8.1f} ms"
            f"\n    {access_pct:3.0%}  access : {partial_ms:8.1f} ms"
            f"\n    Speedup     : {speedup:8.1f}x"
        )
        assert speedup > 2, f"Expected >2x speedup for 10% access, got {speedup:.1f}x"


# ---------------------------------------------------------------------------
# 2. In-process LRU cache: zero-deser reads vs pickle round-trip
# ---------------------------------------------------------------------------

class TestInProcessCachePerf:
    """Compare get_state from in-process cache vs pickle deserialization."""

    N = 5_000

    @pytest.mark.asyncio
    async def test_lru_hit_faster_than_pickle_roundtrip(self):
        """L1 cache hit should be massively faster than pickle.loads."""

        stored = _make_stored_state("wf-bench")

        # Pickle round-trip
        pickled = pickle.dumps(stored)
        t0 = time.perf_counter()
        for _ in range(self.N):
            pickle.loads(pickled)
        pickle_ms = (time.perf_counter() - t0) * 1000

        # LRU cache hit (zero deser)
        cache = InProcessEuphemeralStorage(max_size=100)
        await cache.put_state(stored)
        t0 = time.perf_counter()
        for _ in range(self.N):
            await cache.get_state("wf-bench")
        cache_ms = (time.perf_counter() - t0) * 1000

        speedup = pickle_ms / cache_ms if cache_ms > 0 else float("inf")
        print(
            f"\n  LRU hit vs pickle.loads ({self.N} reads):"
            f"\n    pickle.loads : {pickle_ms:8.1f} ms"
            f"\n    LRU hit     : {cache_ms:8.1f} ms"
            f"\n    Speedup     : {speedup:8.1f}x"
        )
        assert speedup > 5, f"Expected >5x speedup, got {speedup:.1f}x"

    @pytest.mark.asyncio
    async def test_pickle_faster_than_pydantic_json(self):
        """pickle round-trip should be faster than Pydantic JSON round-trip."""

        stored = _make_stored_state("wf-bench")

        # Pydantic JSON round-trip
        json_bytes = stored.model_dump_json().encode()
        adapter = TypeAdapter(StoredState[PerfState])
        t0 = time.perf_counter()
        for _ in range(self.N):
            adapter.validate_json(json_bytes)
        pydantic_ms = (time.perf_counter() - t0) * 1000

        # Pickle round-trip
        pickled = pickle.dumps(stored)
        t0 = time.perf_counter()
        for _ in range(self.N):
            pickle.loads(pickled)
        pickle_ms = (time.perf_counter() - t0) * 1000

        speedup = pydantic_ms / pickle_ms if pickle_ms > 0 else float("inf")
        print(
            f"\n  Pickle vs Pydantic JSON ({self.N} round-trips):"
            f"\n    Pydantic JSON : {pydantic_ms:8.1f} ms"
            f"\n    pickle        : {pickle_ms:8.1f} ms"
            f"\n    Speedup       : {speedup:8.1f}x"
        )
        assert speedup > 1.5, f"Expected >1.5x speedup, got {speedup:.1f}x"


# ---------------------------------------------------------------------------
# 3. String-based event routing vs isinstance
# ---------------------------------------------------------------------------

class TestRoutingPerf:
    """String comparison routing vs isinstance + full body validation."""

    N = 10_000

    def test_string_routing_faster_than_isinstance(self):
        """Routing by event_type string should be faster than deserialising to isinstance."""
        now = datetime.datetime.now()
        raw = _make_event_dict(0)

        events = [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=i,
                global_id=i,
                at=now,
                workflow_type="bench",
                event_type="perf_event",
                _raw_body=dict(raw),
                _body_validator=_validate_perf_event,
            )
            for i in range(self.N)
        ]

        # String routing (no validation triggered)
        t0 = time.perf_counter()
        matched_str = 0
        for ev in events:
            if ev.event_type == "perf_event":
                matched_str += 1
        string_ms = (time.perf_counter() - t0) * 1000

        # isinstance routing (triggers full validation on every event)
        events2 = [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=i,
                global_id=i,
                at=now,
                workflow_type="bench",
                event_type="perf_event",
                _raw_body=dict(raw),
                _body_validator=_validate_perf_event,
            )
            for i in range(self.N)
        ]

        t0 = time.perf_counter()
        matched_isinstance = 0
        for ev in events2:
            if isinstance(ev.event, PerfEvent):
                matched_isinstance += 1
        isinstance_ms = (time.perf_counter() - t0) * 1000

        speedup = isinstance_ms / string_ms if string_ms > 0 else float("inf")
        assert matched_str == matched_isinstance == self.N
        print(
            f"\n  String routing vs isinstance ({self.N} events):"
            f"\n    isinstance (validate) : {isinstance_ms:8.1f} ms"
            f"\n    string compare        : {string_ms:8.1f} ms"
            f"\n    Speedup              : {speedup:8.1f}x"
        )
        assert speedup > 5, f"Expected >5x speedup, got {speedup:.1f}x"


# ---------------------------------------------------------------------------
# 4. LRU eviction under pressure: stays bounded
# ---------------------------------------------------------------------------

class TestLRUBoundedness:
    """Verify the LRU cache stays within its max_size under heavy writes."""

    @pytest.mark.asyncio
    async def test_cache_stays_bounded(self):
        max_size = 1_000
        cache = InProcessEuphemeralStorage(max_size=max_size)

        for i in range(max_size * 3):
            await cache.put_state(_make_stored_state(f"wf-{i}", n_items=5))

        assert len(cache._cache) == max_size

    @pytest.mark.asyncio
    async def test_high_throughput_put_get(self):
        """Measure throughput of L1 cache put+get cycles."""
        n = 20_000
        cache = InProcessEuphemeralStorage(max_size=10_000)
        states = [_make_stored_state(f"wf-{i}", n_items=5) for i in range(n)]

        t0 = time.perf_counter()
        for s in states:
            await cache.put_state(s)
        put_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        hits = 0
        for s in states[-10_000:]:
            if await cache.get_state(s.id) is not None:
                hits += 1
        get_ms = (time.perf_counter() - t0) * 1000

        print(
            f"\n  LRU throughput ({n} states, max_size=10k):"
            f"\n    put {n:,} states : {put_ms:8.1f} ms  ({n / put_ms * 1000:,.0f} ops/s)"
            f"\n    get 10k states  : {get_ms:8.1f} ms  ({10_000 / get_ms * 1000:,.0f} ops/s)"
            f"\n    Hits            : {hits:,} / 10,000"
        )
        assert hits == 10_000
