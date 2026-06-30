from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from ze_agents.client import LLMClient
from ze_logging import get_logger
from ze_finance.errors import FinanceParseError
from ze_finance.store import CsvMappingStore
from ze_finance.types import (
    Account,
    AccountType,
    CsvMapping,
    Position,
    Transaction,
    TransactionType,
)

log = get_logger(__name__)

_ANTHROPIC_MODEL = "anthropic/claude-haiku-4-5"

_INFER_PROMPT = """\
You are a bank CSV column mapper. Given CSV headers and sample rows, return a JSON object mapping column names.

Headers: {headers}

Sample rows:
{samples}

Return ONLY a JSON object with these fields (use null for fields not present):
{{
  "date_column": "<column name for transaction date>",
  "amount_column": "<column name if single amount column (positive/negative), else null>",
  "debit_column": "<column name for debit amount if separate, else null>",
  "credit_column": "<column name for credit amount if separate, else null>",
  "description_column": "<column name for description/merchant>",
  "currency_column": "<column name for currency if present, else null>",
  "date_format": "<strftime format string, e.g. %Y-%m-%d>"
}}
"""


class CsvSchemaInferrer:
    """Sends CSV header + 5 sample rows to Anthropic and returns a CsvMapping.
    Called once per source_id; result is persisted and reused on subsequent imports.
    """

    def __init__(self, client: LLMClient, mapping_store: CsvMappingStore) -> None:
        self._client = client
        self._store = mapping_store

    async def infer(self, source_id: str, header: list[str], samples: list[list[str]]) -> CsvMapping:
        cached = await self._store.get(source_id)
        if cached:
            return cached
        mapping = await self._call_llm(source_id, header, samples)
        await self._store.upsert(source_id, mapping)
        return mapping

    async def _call_llm(self, source_id: str, header: list[str], samples: list[list[str]]) -> CsvMapping:
        sample_text = "\n".join(", ".join(row) for row in samples[:5])
        prompt = _INFER_PROMPT.format(headers=", ".join(header), samples=sample_text)
        response = await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=_ANTHROPIC_MODEL,
        )
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            data: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FinanceParseError(f"Could not infer column mapping: {exc}") from exc

        amount_col = data.get("amount_column")
        if not amount_col and not (data.get("debit_column") and data.get("credit_column")):
            raise FinanceParseError("Could not infer column mapping: no amount column identified")

        return CsvMapping(
            source_id=source_id,
            date_column=data["date_column"],
            amount_column=amount_col or "",
            description_column=data["description_column"],
            date_format=data.get("date_format", "%Y-%m-%d"),
            debit_column=data.get("debit_column"),
            credit_column=data.get("credit_column"),
            currency_column=data.get("currency_column"),
            inferred_at=datetime.now(timezone.utc),
        )


class CsvDataSource:
    """DataSource for bank CSV exports."""

    def __init__(
        self,
        source_id: str,
        account_id: str,
        account_name: str,
        currency: str,
        mapping: CsvMapping,
        rows: list[dict[str, str]],
    ) -> None:
        self._source_id = source_id
        self._account_id = account_id
        self._account_name = account_name
        self._currency = currency
        self._mapping = mapping
        self._rows = rows

    @property
    def source_id(self) -> str:
        return self._source_id

    async def fetch_account(self) -> Account:
        balance = Decimal("0")
        return Account(
            id=self._account_id,
            source_id=self._source_id,
            account_type=AccountType.BANK,
            name=self._account_name,
            currency=self._currency,
            balance=balance,
            updated_at=datetime.now(timezone.utc),
        )

    async def fetch_positions(self) -> list[Position]:
        return []

    async def fetch_transactions(self, since: datetime) -> list[Transaction]:
        m = self._mapping
        transactions: list[Transaction] = []

        for row_idx, row in enumerate(self._rows, start=2):
            try:
                date_str = row.get(m.date_column, "").strip()
                settled_at = datetime.strptime(date_str, m.date_format).replace(tzinfo=timezone.utc)
            except (ValueError, KeyError) as exc:
                raise FinanceParseError(f"Date parse error at row {row_idx}: {exc}") from exc

            if settled_at < since:
                continue

            try:
                if m.amount_column and m.amount_column in row:
                    raw_amount = row[m.amount_column].strip().replace(",", ".")
                    amount = Decimal(raw_amount)
                elif m.debit_column and m.credit_column:
                    debit_str = row.get(m.debit_column, "0").strip().replace(",", ".") or "0"
                    credit_str = row.get(m.credit_column, "0").strip().replace(",", ".") or "0"
                    amount = Decimal(credit_str) - Decimal(debit_str)
                else:
                    raise FinanceParseError(f"No amount column resolvable at row {row_idx}")
            except InvalidOperation as exc:
                raise FinanceParseError(f"Amount parse error at row {row_idx}: {exc}") from exc

            description = row.get(m.description_column, "").strip()
            currency = (row.get(m.currency_column, self._currency) if m.currency_column else self._currency).strip() or self._currency

            tx_type = TransactionType.DEPOSIT if amount >= 0 else TransactionType.WITHDRAWAL

            external_id = hashlib.sha256(
                f"{date_str}:{amount}:{description}".encode()
            ).hexdigest()[:16]

            transactions.append(Transaction(
                id=f"{self._source_id}:{external_id}",
                account_id=self._account_id,
                transaction_type=tx_type,
                asset=None,
                quantity=abs(amount),
                price=Decimal("1"),
                fees=Decimal("0"),
                currency=currency,
                settled_at=settled_at,
                notes=description,
            ))

        return transactions


def parse_csv_content(content: str) -> tuple[list[str], list[list[str]], list[dict[str, str]]]:
    """Return (header, sample_rows, all_rows_as_dicts)."""
    content = content.lstrip("﻿")
    dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;")
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    header = reader.fieldnames or []
    all_rows = list(reader)
    sample_rows = [[row.get(h, "") for h in header] for row in all_rows[:5]]
    return list(header), sample_rows, all_rows
