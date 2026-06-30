from __future__ import annotations

from ze_finance.categoriser import CategoryInferrer


def _inferrer(llm_enabled: bool = False) -> CategoryInferrer:
    return CategoryInferrer(client=None, llm_enabled=llm_enabled)


def test_keyword_food():
    inf = _inferrer()
    assert inf.infer_keyword("UBER EATS LONDON") == "Food & Dining"


def test_keyword_transport():
    inf = _inferrer()
    assert inf.infer_keyword("RYANAIR FLIGHT FR1234") == "Transport"


def test_keyword_entertainment():
    inf = _inferrer()
    assert inf.infer_keyword("NETFLIX.COM") == "Entertainment"


def test_keyword_other():
    inf = _inferrer()
    assert inf.infer_keyword("SOMETHING UNKNOWN XYZ") == "Other"


async def test_infer_batch_no_llm():
    inf = _inferrer()
    descriptions = ["UBER EATS", "NETFLIX", "RANDOM MERCHANT"]
    results = await inf.infer_batch(descriptions)
    assert results[0] == "Food & Dining"
    assert results[1] == "Entertainment"
    assert results[2] == "Other"
