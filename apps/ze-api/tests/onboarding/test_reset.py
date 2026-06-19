from __future__ import annotations

import pytest

from ze_api.errors import OnboardingError
from ze_onboarding import ResetService


async def test_reset_requires_explicit_confirmation():
    service = ResetService(pool=object())

    with pytest.raises(OnboardingError):
        await service.reset("memory", confirm="yes")
