"""Tests for dream/sensitive.py — sensitive entity classification."""

from __future__ import annotations

from ze_memory.dream.sensitive import is_sensitive_entity


def test_financial_entity_type_is_sensitive():
    assert is_sensitive_entity("bank", "Main Street Branch", {})


def test_health_keyword_in_name_is_sensitive():
    assert is_sensitive_entity("person", "Dr. Ana Medication Plan", {})


def test_credential_keyword_in_attrs_is_sensitive():
    assert is_sensitive_entity(
        "service",
        "GitHub",
        {"note": "stores the api key for deployments"},
    )


def test_benign_entity_is_not_sensitive():
    assert not is_sensitive_entity("org", "Acme Corp", {"industry": "software"})
