import logging

import pytest
import structlog


@pytest.fixture(autouse=True)
def _configure_test_logging():
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
    )
