from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from ze_agents.client import LLMClient
from ze_logging import get_logger
from ze_ingestion.types import ContentType, ExtractionResult, ProcessedContent
from ze_finance.errors import FinanceParseError
from ze_finance.sources.csv import CsvSchemaInferrer, CsvDataSource, parse_csv_content
from ze_finance.store import TransactionStore
from ze_finance.types import (
    Account,
    AccountType,
    Asset,
    AssetClass,
    Transaction,
    TransactionType,
)

log = get_logger(__name__)

content_types = [ContentType.PDF, ContentType.PLAIN_TEXT, ContentType.DOCUMENT]

_EXTRACT_PROMPT = """\
You are a financial data extraction assistant. Extract all transactions from the \
bank statement or financial document below.

Return a JSON array where each element is:
{
  "date": "YYYY-MM-DD",
  "amount": <float, positive=credit, negative=debit>,
  "currency": "GBP",
  "description": "Merchant or transfer description",
  "type": "deposit|withdrawal|fee|interest|transfer"
}

Return ONLY the JSON array, no explanation. If no transactions are found, return [].

Document:
"""

_INGEST_ACCOUNT_PREFIX = "ingested"


def _stable_account_id(source_url: str | None, content_hash: str) -> str:
    key = source_url or content_hash
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"{_INGEST_ACCOUNT_PREFIX}:{digest}"


def _account_label(source_url: str | None) -> str:
    if source_url:
        parts = source_url.rstrip("/").split("/")
        return parts[-1] or source_url
    return "Imported statement"


class FinanceIngestionExtractor:
    """
    Intercepts PDF and CSV content during ingestion and writes structured
    Transaction rows into finance_transactions rather than only fact strings.

    The extractor also returns an ExtractionResult so the ingestion pipeline
    can push a summary and high-level facts to ze-memory as usual.
    """

    content_types: list[ContentType] = content_types

    def __init__(
        self,
        transaction_store: TransactionStore,
        llm_client: LLMClient,
        model: str,
        csv_inferrer: CsvSchemaInferrer,
    ) -> None:
        self._store = transaction_store
        self._client = llm_client
        self._model = model
        self._csv_inferrer = csv_inferrer

    async def extract(self, content: ProcessedContent) -> ExtractionResult:
        transactions = await self._parse(content)
        if not transactions:
            return ExtractionResult(summary="No transactions found.", facts=[], entities=[], tags=["finance"])

        inserted = await self._store.append(transactions)

        facts = [_tx_to_fact(tx) for tx in transactions]
        summary = (
            f"Ingested {len(transactions)} transactions "
            f"({inserted} new) from {content.source_url or 'uploaded file'}."
        )
        log.info(
            "finance_ingestion_extractor_done",
            total=len(transactions),
            inserted=inserted,
            source=content.source_url,
        )
        return ExtractionResult(
            summary=summary,
            facts=facts,
            entities=[],
            tags=["finance", "transactions"],
            metadata={"transactions_total": len(transactions), "transactions_inserted": inserted},
        )

    async def _parse(self, content: ProcessedContent) -> list[Transaction]:
        text = content.text.strip()
        if not text:
            return []

        # Try CSV path first for plain text / document content
        if content.content_type in (ContentType.PLAIN_TEXT, ContentType.DOCUMENT):
            try:
                return await self._parse_csv(content)
            except (FinanceParseError, Exception):
                pass  # fall through to LLM path

        return await self._parse_llm(content)

    async def _parse_csv(self, content: ProcessedContent) -> list[Transaction]:
        header, samples, all_rows = parse_csv_content(content.text)
        if not header:
            raise FinanceParseError("No CSV header found")

        content_hash = hashlib.sha256(content.text[:512].encode()).hexdigest()[:12]
        source_id = content.source_url or f"csv:{content_hash}"
        account_id = _stable_account_id(content.source_url, content_hash)

        mapping = await self._csv_inferrer.infer(source_id, header, samples)
        source = CsvDataSource(
            source_id=source_id,
            account_id=account_id,
            account_name=_account_label(content.source_url),
            currency=mapping.currency_column or "GBP",
            mapping=mapping,
            rows=all_rows,
        )
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        return await source.fetch_transactions(since=since)

    async def _parse_llm(self, content: ProcessedContent) -> list[Transaction]:
        text = content.text[:12_000]
        response = await self._client.complete(
            model=self._model,
            messages=[{"role": "user", "content": _EXTRACT_PROMPT + text}],
        )
        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        try:
            items: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("finance_ingestion_llm_parse_failed", source=content.source_url)
            return []

        content_hash = hashlib.sha256(content.text[:512].encode()).hexdigest()[:12]
        account_id = _stable_account_id(content.source_url, content_hash)
        transactions: list[Transaction] = []

        for i, item in enumerate(items):
            try:
                tx = _item_to_transaction(item, account_id, i)
                transactions.append(tx)
            except (KeyError, InvalidOperation, ValueError) as exc:
                log.warning("finance_ingestion_tx_parse_error", index=i, error=str(exc))

        return transactions


def _item_to_transaction(item: dict[str, Any], account_id: str, index: int) -> Transaction:
    date_str = item["date"]
    settled_at = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    amount = Decimal(str(item["amount"]))
    currency = item.get("currency", "GBP")
    description = item.get("description", "")
    tx_type_str = item.get("type", "deposit" if amount >= 0 else "withdrawal")
    tx_type = TransactionType(tx_type_str) if tx_type_str in TransactionType._value2member_map_ else (
        TransactionType.DEPOSIT if amount >= 0 else TransactionType.WITHDRAWAL
    )

    digest = hashlib.sha256(f"{date_str}:{amount}:{description}:{index}".encode()).hexdigest()[:16]
    return Transaction(
        id=f"{account_id}:{digest}",
        account_id=account_id,
        transaction_type=tx_type,
        asset=None,
        quantity=abs(amount),
        price=Decimal("1"),
        fees=Decimal("0"),
        currency=currency,
        settled_at=settled_at,
        notes=description,
    )


def _tx_to_fact(tx: Transaction) -> str:
    sign = "+" if tx.transaction_type in (TransactionType.DEPOSIT, TransactionType.INTEREST) else "-"
    return (
        f"{sign}{tx.currency} {tx.quantity:.2f} "
        f"on {tx.settled_at.date()} — {tx.notes or tx.transaction_type.value}"
    )
