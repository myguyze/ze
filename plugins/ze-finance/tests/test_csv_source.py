from __future__ import annotations

import pytest
from datetime import datetime, timezone

from ze_finance.sources.csv import parse_csv_content, CsvDataSource
from ze_finance.types import CsvMapping, TransactionType


@pytest.fixture
def simple_mapping() -> CsvMapping:
    return CsvMapping(
        source_id="csv:test",
        date_column="Date",
        amount_column="Amount",
        description_column="Description",
        date_format="%Y-%m-%d",
    )


def test_parse_csv_content():
    content = (
        "Date,Description,Amount\n2026-01-01,ALDI,-34.20\n2026-01-02,SALARY,2800.00"
    )
    header, samples, rows = parse_csv_content(content)
    assert header == ["Date", "Description", "Amount"]
    assert len(rows) == 2
    assert len(samples) == 2


async def test_csv_data_source_parses_transactions(simple_mapping):
    content = (
        "Date,Description,Amount\n2026-01-01,ALDI,-34.20\n2026-01-02,SALARY,2800.00"
    )
    _, _, rows = parse_csv_content(content)

    source = CsvDataSource(
        source_id="csv:test",
        account_id="test:bank",
        account_name="Test Bank",
        currency="EUR",
        mapping=simple_mapping,
        rows=rows,
    )
    txs = await source.fetch_transactions(
        since=datetime(2025, 1, 1, tzinfo=timezone.utc)
    )
    assert len(txs) == 2
    types = {tx.notes: tx.transaction_type for tx in txs}
    assert types["ALDI"] == TransactionType.WITHDRAWAL
    assert types["SALARY"] == TransactionType.DEPOSIT


async def test_csv_since_filter(simple_mapping):
    content = "Date,Description,Amount\n2026-01-01,OLD,-10.00\n2026-06-01,NEW,-10.00"
    _, _, rows = parse_csv_content(content)
    source = CsvDataSource(
        source_id="csv:test",
        account_id="test:bank",
        account_name="Test Bank",
        currency="EUR",
        mapping=simple_mapping,
        rows=rows,
    )
    txs = await source.fetch_transactions(
        since=datetime(2026, 3, 1, tzinfo=timezone.utc)
    )
    assert len(txs) == 1
    assert txs[0].notes == "NEW"
