"""Merge 003_user_facts_embedding and 003w_workflows branches

Revision ID: 003m
Revises: 003, 003w
Create Date: 2026-05-22
"""
from typing import Sequence, Union

revision: str = "003m"
down_revision: Union[str, Sequence[str], None] = ("003", "003w")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
