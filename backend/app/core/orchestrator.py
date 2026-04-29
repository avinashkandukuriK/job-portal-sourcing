"""Sourcing orchestrator.

Takes a parsed JD + selected adapters, fans out, scores, dedupes, persists.

Flow per search:
1. Build instances of selected adapters (filtered by tier/active state).
2. Run each adapter's `search()` concurrently with timeout + error capture.
3. Per-adapter run log written to `adapter_run_log`.
4. Candidates upserted to `candidates` (smart dedup by source pair / phone / email).
5. Each candidate scored against the JD via `scorer.score_candidate`.
6. Cross-adapter dedup using Candidate.dedupe_key.
7. Search row + search_results rows persisted.
8. Return SearchResult with scored, ranked candidates and per-adapter stats.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.adapters import (
    AdapterTier,
    SourceAdapter,
    build_enabled_instances,
)
from app.adapters.toggle_store import get_toggle_store
from app.db.repository import (
    save_adapter_run_log,
    save_search,
    save_search_results,
    upsert_candidate,
)
from app.models import (
    AdapterRunStats,
    Candidate,
    ParsedJD,
    ScoredCandidate,
    SearchResult,
)

from .scorer import score_candidate

logger = logging.getLogger(__name__)

ADAPTER_TIMEOUT_S = 45


class SourcingOrchestrator:
    """Coordinates a single search run end to end."""

    def __init__(
        self,
        *,
        job_order_id: Optional[str] = None,
        user_id: Optional[str] = None,
        raw_jd_text: Optional[str] = None,
        persist: bool = True,
    ) -> None:
        self.job_order_id = job_order_id
        self.user_id = user_id
        self.raw_jd_text = raw_jd_text
        self.persist = persist

    # ---------------- main entry ----------------

    async def run(
        self,
        jd: ParsedJD,
        *,
        mode: str = "internal_external",
        selected_adapter_names: Optional[list[str]] = None,
        include_premium: bool = False,
        limit_per_source: int = 25,
    ) -> SearchResult:
        t0 = time.monotonic()

        # Resolve which adapters to run
        adapters = await self._resolve_adapters(
            mode=mode,
            names=selected_adapter_names,
            include_premium=include_premium,
        )
        if not adapters:
            logger.warning("No active adapters resolved for mode=%s names=%s", mode, selected_adapter_names)

        # Fan out
        per_adapter = await self._run_adapters(adapters, jd, limit_per_source)

        # Score + dedupe
        scored = self._score_and_dedupe(per_adapter, jd)

        # Persist
        search_id = await self._persist(jd, per_adapter, scored, mode, t0)

        duration_ms = int((time.monotonic() - t0) * 1000)
        adapter_stats = [s["stats"] for s in per_adapter]
        result = SearchResult(
            id=search_id,
            parsed_jd=jd,
            candidates=scored,
            adapter_stats=adapter_stats,
        )
        logger.info(
            "Search complete: %d candidates from %d adapters in %dms",
            len(scored), len(per_adapter), duration_ms,
        )
        # Cleanly close adapter clients
        for a in adapters:
            try:
                await a.aclose()
            except Exception:  # noqa: BLE001
                pass
        return result

    # ---------------- internals ----------------

    async def _resolve_adapters(
        self,
        *,
        mode: str,
        names: Optional[list[str]],
        include_premium: bool,
    ) -> list[SourceAdapter]:
        """Build the list of adapter instances to run, honoring mode + toggle state."""

        if mode == "internal":
            all_inst = await build_enabled_instances(tier=AdapterTier.INTERNAL)
        elif mode == "external":
            non_prem = await build_enabled_instances(tier=AdapterTier.NON_PREMIUM)
            prem = await build_enabled_instances(tier=AdapterTier.PREMIUM) if include_premium else []
            all_inst = non_prem + prem
        else:  # internal_external
            internal = await build_enabled_instances(tier=AdapterTier.INTERNAL)
            non_prem = await build_enabled_instances(tier=AdapterTier.NON_PREMIUM)
            prem = await build_enabled_instances(tier=AdapterTier.PREMIUM) if include_premium else []
            all_inst = internal + non_prem + prem

        # If user gave explicit names, filter
        if names:
            wanted = set(names)
            kept = [a for a in all_inst if a.metadata.name in wanted]
            for a in all_inst:
                if a.metadata.name not in wanted:
                    await a.aclose()
            return kept
        return all_inst

    async def _run_adapters(
        self,
        adapters: list[SourceAdapter],
        jd: ParsedJD,
        limit: int,
    ) -> list[dict]:
        """Run all adapters concurrently. Returns list of {adapter, stats, candidates}."""
        sem = asyncio.Semaphore(8)

        async def _one(a: SourceAdapter) -> dict:
            stats = AdapterRunStats(source=a.metadata.name, enabled=True)
            t0 = time.monotonic()
            cands: list[Candidate] = []
            try:
                async with sem:
                    cands = await asyncio.wait_for(a.search(jd, limit=limit), timeout=ADAPTER_TIMEOUT_S)
                stats.candidates_found = len(cands)
                # Reset failure counter on success
                try:
                    get_toggle_store().record_success(a.metadata.name)
                except Exception:  # noqa: BLE001
                    pass
            except asyncio.TimeoutError:
                stats.error = "Timeout"
                logger.warning("Adapter %s timed out after %ds", a.metadata.name, ADAPTER_TIMEOUT_S)
                try:
                    get_toggle_store().record_failure(a.metadata.name)
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                stats.error = str(exc)
                logger.exception("Adapter %s failed: %s", a.metadata.name, exc)
                try:
                    get_toggle_store().record_failure(a.metadata.name)
                except Exception:  # noqa: BLE001
                    pass
            stats.duration_ms = int((time.monotonic() - t0) * 1000)
            return {"adapter": a, "stats": stats, "candidates": cands}

        return await asyncio.gather(*[_one(a) for a in adapters])

    def _score_and_dedupe(
        self,
        per_adapter: list[dict],
        jd: ParsedJD,
    ) -> list[ScoredCandidate]:
        """Cross-adapter dedup + scoring + ranking."""
        merged: dict[str, ScoredCandidate] = {}
        for entry in per_adapter:
            for cand in entry["candidates"]:
                key = cand.dedupe_key
                scored = score_candidate(cand, jd)
                if key in merged:
                    # Keep the higher-scored record; merge contact info
                    existing = merged[key]
                    if scored.score > existing.score:
                        # Merge missing contact bits from existing into new
                        new_c = scored.candidate
                        old_c = existing.candidate
                        new_c.contact.email = new_c.contact.email or old_c.contact.email
                        new_c.contact.phone = new_c.contact.phone or old_c.contact.phone
                        merged[key] = scored
                else:
                    merged[key] = scored

        ranked = sorted(merged.values(), key=lambda s: s.score, reverse=True)
        return ranked

    async def _persist(
        self,
        jd: ParsedJD,
        per_adapter: list[dict],
        scored: list[ScoredCandidate],
        mode: str,
        t0: float,
    ) -> Optional[str]:
        if not self.persist:
            return None

        adapter_names = [e["adapter"].metadata.name for e in per_adapter]
        duration_ms = int((time.monotonic() - t0) * 1000)
        total_cost = 0.0  # adapter_run_log will accumulate per-call costs later

        search_id = await save_search(
            job_order_id=self.job_order_id,
            user_id=self.user_id,
            raw_jd_text=self.raw_jd_text,
            parsed_jd=jd,
            mode=mode,
            selected_adapters=adapter_names,
            candidate_count=len(scored),
            duration_ms=duration_ms,
            total_cost_usd=total_cost,
        )
        if not search_id:
            return None

        # Per-adapter run log
        for entry in per_adapter:
            stats = entry["stats"]
            await save_adapter_run_log(
                search_id=search_id,
                adapter_name=stats.source,
                candidates_returned=stats.candidates_found,
                duration_ms=stats.duration_ms,
                error_message=stats.error,
            )

        # Upsert candidates + collect search_results rows
        result_rows: list[dict] = []
        for rank, sc in enumerate(scored, start=1):
            cid = await upsert_candidate(sc.candidate)
            if not cid:
                continue
            result_rows.append({
                "candidate_id": cid,
                "adapter_name": sc.candidate.source,
                "score": sc.score,
                "score_breakdown": sc.score_breakdown,
                "reasoning": sc.reasoning,
                "rank": rank,
            })
        await save_search_results(search_id=search_id, scored=result_rows)
        return search_id
