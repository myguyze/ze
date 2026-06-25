from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from datetime import datetime
from typing import Protocol

import numpy as np

from ze_agents.nli import NLIClient
from ze_finance.recurring.types import RecurringExpense, RecurringStatus, snap_interval
from ze_finance.types import Transaction, TransactionType

_MIN_OCCURRENCES     = 2   # minimum number of transactions to consider
_AMOUNT_TOLERANCE    = 0.10  # max coefficient of variation on amounts
_GAP_TOLERANCE       = 0.40  # gaps must be within ±40% of the median gap
                              # (billing dates drift; months differ in length)
_MIN_SPAN_FACTOR     = 1.5   # total date span must be ≥ 1.5× detected interval
_MIN_ABSOLUTE_SPAN   = 14    # span must be at least 14 days regardless of interval


class TextEmbedder(Protocol):
    def encode(self, texts: list[str] | str) -> object: ...


def _normalise(description: str) -> str:
    s = description.lower()
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _median_decimal(values: list[Decimal]) -> Decimal:
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def _detect_interval(dates: list[datetime]) -> int | None:
    """
    Derive the dominant billing interval from a sorted list of occurrence dates.

    Returns the snapped interval in days, or None if no consistent pattern exists.
    Gaps must all be within ±GAP_TOLERANCE of the median gap, which filters out
    merchants with erratic timing (e.g. alternating weekly/monthly charges).
    """
    sorted_dates = sorted(dates)
    gaps = [
        (sorted_dates[i + 1] - sorted_dates[i]).days
        for i in range(len(sorted_dates) - 1)
    ]
    if not gaps:
        return None

    sorted_gaps = sorted(gaps)
    median_gap = sorted_gaps[len(sorted_gaps) // 2]
    if median_gap < 1:
        return None

    # Reject if any gap falls outside the tolerance band around the median.
    for g in gaps:
        if abs(g - median_gap) / median_gap > _GAP_TOLERANCE:
            return None

    return snap_interval(median_gap)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class RecurringDetector:
    """Pure detector — optional async NLI merchant merge before grouping."""

    _SPENDING_TYPES = {TransactionType.WITHDRAWAL, TransactionType.FEE}

    def __init__(
        self,
        *,
        embedder: TextEmbedder | None = None,
        nli_client: NLIClient | None = None,
        nli_merchant_merge_enabled: bool = False,
        nli_merchant_cosine_threshold: float = 0.70,
        nli_merchant_entailment_threshold: float = 0.70,
    ) -> None:
        self._embedder = embedder
        self._nli_client = nli_client
        self._nli_merchant_merge_enabled = nli_merchant_merge_enabled
        self._nli_merchant_cosine_threshold = nli_merchant_cosine_threshold
        self._nli_merchant_entailment_threshold = nli_merchant_entailment_threshold

    async def detect_transactions(
        self,
        transactions: list[Transaction],
    ) -> list[RecurringExpense]:
        merge_maps: dict[tuple[str, str], dict[str, str]] = {}
        if (
            self._nli_merchant_merge_enabled
            and self._embedder is not None
            and self._nli_client is not None
        ):
            merge_maps = await self._build_merge_maps(transactions)
        return self.detect(transactions, merge_maps=merge_maps)

    async def _build_merge_maps(
        self,
        transactions: list[Transaction],
    ) -> dict[tuple[str, str], dict[str, str]]:
        buckets: dict[tuple[str, str], list[str]] = {}
        for tx in transactions:
            if tx.transaction_type not in self._SPENDING_TYPES or not tx.notes:
                continue
            key = (tx.currency, tx.account_id)
            buckets.setdefault(key, []).append(tx.notes)

        merge_maps: dict[tuple[str, str], dict[str, str]] = {}
        for bucket_key, descriptions in buckets.items():
            merge_map = await self._merge_aliases_in_bucket(descriptions)
            if merge_map:
                merge_maps[bucket_key] = merge_map
        return merge_maps

    async def _merge_aliases_in_bucket(
        self,
        descriptions: list[str],
    ) -> dict[str, str]:
        unique = list(dict.fromkeys(descriptions))
        if len(unique) < 2:
            return {}

        norms = [_normalise(d) for d in unique]
        if len(set(norms)) < 2:
            return {}

        embeddings = self._embedder.encode(unique)  # type: ignore[union-attr]
        parent = {norm: norm for norm in norms}

        def find(node: str) -> str:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a: str, b: str) -> None:
            root_a, root_b = find(a), find(b)
            if root_a == root_b:
                return
            if root_a < root_b:
                parent[root_b] = root_a
            else:
                parent[root_a] = root_b

        pairs_to_score: list[tuple[str, str]] = []
        pair_norms: list[tuple[str, str]] = []

        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                if norms[i] == norms[j]:
                    union(norms[i], norms[j])
                    continue
                cos = _cosine(
                    np.array(embeddings[i], dtype=float),
                    np.array(embeddings[j], dtype=float),
                )
                if cos < self._nli_merchant_cosine_threshold:
                    continue
                pairs_to_score.append((unique[i], unique[j]))
                pairs_to_score.append((unique[j], unique[i]))
                pair_norms.append((norms[i], norms[j]))

        if pairs_to_score:
            scores = await self._nli_client.scores(pairs_to_score)  # type: ignore[union-attr]
            for idx, (norm_a, norm_b) in enumerate(pair_norms):
                fwd = scores[idx * 2]
                bwd = scores[idx * 2 + 1]
                entailment = max(
                    (fwd or {}).get("entailment", 0.0),
                    (bwd or {}).get("entailment", 0.0),
                )
                if entailment >= self._nli_merchant_entailment_threshold:
                    union(norm_a, norm_b)

        merge_map: dict[str, str] = {}
        for norm in norms:
            root = find(norm)
            if root != norm:
                merge_map[norm] = root
        return merge_map

    def detect(
        self,
        transactions: list[Transaction],
        *,
        merge_maps: dict[tuple[str, str], dict[str, str]] | None = None,
    ) -> list[RecurringExpense]:
        spending = [
            tx for tx in transactions
            if tx.transaction_type in self._SPENDING_TYPES and tx.notes
        ]

        groups: dict[tuple[str, str, str], list[Transaction]] = {}
        for tx in spending:
            norm = _normalise(tx.notes)
            bucket_map = (merge_maps or {}).get((tx.currency, tx.account_id), {})
            norm = bucket_map.get(norm, norm)
            key = (norm, tx.currency, tx.account_id)
            groups.setdefault(key, []).append(tx)

        results: list[RecurringExpense] = []
        for (norm_key, currency, account_id), txs in groups.items():
            if len(txs) < _MIN_OCCURRENCES:
                continue

            sorted_txs = sorted(txs, key=lambda t: t.settled_at)

            interval_days = _detect_interval([tx.settled_at for tx in sorted_txs])
            if interval_days is None:
                continue

            # Enough history to confirm the pattern completed at least once.
            span = (sorted_txs[-1].settled_at - sorted_txs[0].settled_at).days
            if span < max(interval_days * _MIN_SPAN_FACTOR, _MIN_ABSOLUTE_SPAN):
                continue

            amounts = [abs(tx.quantity * tx.price) for tx in txs]
            mean_amount = sum(amounts) / len(amounts)
            if mean_amount == 0:
                continue

            variance = sum((a - mean_amount) ** 2 for a in amounts) / len(amounts)
            cv = (variance ** Decimal("0.5")) / mean_amount
            if cv > Decimal(str(_AMOUNT_TOLERANCE)):
                continue

            display = Counter(tx.notes for tx in txs).most_common(1)[0][0]
            median_amount = _median_decimal(amounts)

            results.append(
                RecurringExpense(
                    normalised_key=norm_key,
                    account_id=account_id,
                    merchant_display=display,
                    amount=median_amount.quantize(Decimal("0.01")),
                    currency=currency,
                    interval_days=interval_days,
                    category="Other",
                    status=RecurringStatus.DETECTED,
                    first_seen_at=sorted_txs[0].settled_at,
                    last_seen_at=sorted_txs[-1].settled_at,
                    occurrence_count=len(txs),
                )
            )

        return results
