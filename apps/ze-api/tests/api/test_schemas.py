import uuid

import pytest
from pydantic import ValidationError

from ze_api.api.schemas import (
    CapabilityModeUpdate,
    FactReviewRequest,
)
from ze_api.logging import configure_logging


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


def test_capability_mode_update_valid():
    m = CapabilityModeUpdate(mode="autonomous")
    assert m.mode == "autonomous"


def test_capability_mode_update_invalid():
    with pytest.raises(ValidationError):
        CapabilityModeUpdate(mode="full_send")


def test_fact_review_request_confirm():
    req = FactReviewRequest(actions=[{
        "id": str(uuid.uuid4()),
        "action": "confirm",
    }])
    assert req.actions[0].action == "confirm"


def test_fact_review_request_invalid_action():
    with pytest.raises(ValidationError):
        FactReviewRequest(actions=[{
            "id": str(uuid.uuid4()),
            "action": "maybe",
        }])
