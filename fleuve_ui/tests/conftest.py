"""Fixtures for Fleuve UI tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture
def mock_session_maker():
    """Create a mock async session maker."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    session.scalar = AsyncMock(return_value=None)
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=session)
    maker.return_value.__aexit__ = AsyncMock(return_value=None)
    return maker


@pytest.fixture
def mock_event_model():
    """Mock StoredEvent model with workflow_type attribute."""
    model = MagicMock()
    model.workflow_id = MagicMock()
    model.workflow_type = MagicMock()
    model.workflow_version = MagicMock()
    model.global_id = MagicMock()
    model.body = MagicMock()
    model.at = MagicMock()
    return model
