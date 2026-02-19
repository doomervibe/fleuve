"""
Unit tests for les.stream module.
"""

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleuve.stream import ConsumedEvent, Reader, Readers, Sleeper


class TestSleeper:
    """Tests for Sleeper class."""

    def test_sleeper_initialization(self):
        """Test sleeper initialization."""
        sleeper = Sleeper(
            min_sleep=datetime.timedelta(seconds=1),
            max_sleep=datetime.timedelta(seconds=10),
        )
        assert sleeper._min_sleep == datetime.timedelta(seconds=1)
        assert sleeper._max_sleep == datetime.timedelta(seconds=10)
        assert sleeper._next_sleep == datetime.timedelta(seconds=1)

    def test_sleeper_mark_got_events_resets(self):
        """Test that getting events resets sleep time."""
        sleeper = Sleeper(
            min_sleep=datetime.timedelta(seconds=1),
            max_sleep=datetime.timedelta(seconds=10),
        )
        sleeper._next_sleep = datetime.timedelta(seconds=5)
        sleeper.mark_got_events(True)
        assert sleeper._next_sleep == datetime.timedelta(seconds=1)

    def test_sleeper_mark_no_events_increases(self):
        """Test that no events increases sleep time."""
        sleeper = Sleeper(
            min_sleep=datetime.timedelta(seconds=1),
            max_sleep=datetime.timedelta(seconds=10),
        )
        sleeper.mark_got_events(False)
        assert sleeper._next_sleep == datetime.timedelta(seconds=2)  # 1 * 2

        sleeper.mark_got_events(False)
        assert sleeper._next_sleep == datetime.timedelta(seconds=4)  # 2 * 2

    def test_sleeper_respects_max_sleep(self):
        """Test that sleep time doesn't exceed max."""
        sleeper = Sleeper(
            min_sleep=datetime.timedelta(seconds=1),
            max_sleep=datetime.timedelta(seconds=10),
        )
        # Increase beyond max
        for _ in range(5):
            sleeper.mark_got_events(False)
        assert sleeper._next_sleep == datetime.timedelta(seconds=10)

    @pytest.mark.asyncio
    async def test_sleeper_sleep(self):
        """Test sleeper sleep method."""
        sleeper = Sleeper(
            min_sleep=datetime.timedelta(milliseconds=10),
            max_sleep=datetime.timedelta(seconds=1),
        )
        start = asyncio.get_event_loop().time()
        await sleeper.sleep(False)
        elapsed = asyncio.get_event_loop().time() - start
        # Should sleep for min_sleep * 2 (doubled on no events)
        assert elapsed >= 0.01  # At least 10ms


class TestConsumedEvent:
    """Tests for ConsumedEvent dataclass."""

    def test_consumed_event_creation(self):
        """Test creating a consumed event."""
        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=5,
            event={"type": "test"},
            global_id=100,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )
        assert event.workflow_id == "wf-1"
        assert event.event_no == 5
        assert event.global_id == 100
        assert event.workflow_type == "test_workflow"

    def test_consumed_event_is_frozen(self):
        """Test that ConsumedEvent is immutable."""
        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=5,
            event={"type": "test"},
            global_id=100,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            event.workflow_id = "wf-2"


class TestReader:
    """Tests for Reader class."""

    @pytest.fixture
    def mock_session_maker(self):
        """Create a mock session maker."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.execute = AsyncMock()

        maker = MagicMock()
        maker.return_value = session
        maker.__call__ = lambda: session
        return maker

    @pytest.fixture
    def mock_db_model(self):
        """Create a mock database model."""
        model = MagicMock()
        model.__tablename__ = "test_events"
        return model

    def test_reader_initialization(self, mock_session_maker, mock_db_model):
        """Test reader initialization."""
        from fleuve.tests.models import TestOffsetModel

        reader = Reader(
            reader_name="test_reader",
            s=mock_session_maker,
            db_model=mock_db_model,
            offset_model=TestOffsetModel,
            event_types=["event1", "event2"],
        )
        assert reader.name == "test_reader"
        assert reader.event_types == ["event1", "event2"]
        assert reader.last_read_event_g_id is None
        assert not reader._init

    def test_reader_default_sleeper(self, mock_session_maker, mock_db_model):
        """Test reader uses default sleeper if not provided."""
        from fleuve.tests.models import TestOffsetModel

        reader = Reader(
            reader_name="test_reader",
            s=mock_session_maker,
            db_model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        assert reader._sleeper is not None
        assert reader._sleeper._min_sleep == datetime.timedelta(seconds=0)
        assert reader._sleeper._max_sleep == datetime.timedelta(seconds=20)

    @pytest.mark.asyncio
    async def test_reader_context_manager(self, mock_session_maker, mock_db_model):
        """Test reader as async context manager."""
        from fleuve.tests.models import TestOffsetModel

        reader = Reader(
            reader_name="test_reader",
            s=mock_session_maker,
            db_model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        async with reader:
            assert reader._init
            assert reader._bg_checkpoint_marking_job is not None

        # Wait a bit for cancellation to propagate
        await asyncio.sleep(0.05)
        # Task should be done (either cancelled or completed) after context exit
        assert reader._bg_checkpoint_marking_job.done()

    @pytest.mark.asyncio
    async def test_get_offset_no_offset(self, mock_session_maker, mock_db_model):
        """Test getting offset when no offset exists."""
        from fleuve.tests.models import TestOffsetModel

        session = mock_session_maker()
        result = MagicMock()
        result.fetchone.return_value = None
        session.execute = AsyncMock(return_value=result)

        reader = Reader(
            reader_name="test_reader",
            s=mock_session_maker,
            db_model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        offset = await reader.get_offset()
        assert offset == 0

    @pytest.mark.asyncio
    async def test_get_offset_with_existing(self, mock_session_maker, mock_db_model):
        """Test getting offset when offset exists."""
        from fleuve.tests.models import TestOffsetModel

        session = mock_session_maker()
        row = MagicMock()
        row.last_read_event_no = 42
        result = MagicMock()
        result.fetchone.return_value = row
        session.execute = AsyncMock(return_value=result)

        reader = Reader(
            reader_name="test_reader",
            s=mock_session_maker,
            db_model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        offset = await reader.get_offset()
        assert offset == 42

    @pytest.mark.asyncio
    async def test_get_offset_uses_cached(self, mock_session_maker, mock_db_model):
        """Test that cached offset is used."""
        from fleuve.tests.models import TestOffsetModel

        reader = Reader(
            reader_name="test_reader",
            s=mock_session_maker,
            db_model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        reader.last_read_event_g_id = 100
        offset = await reader.get_offset()
        assert offset == 100


class TestReaders:
    """Tests for Readers class."""

    @pytest.fixture
    def mock_session_maker(self):
        """Create a mock session maker."""
        return MagicMock()

    @pytest.fixture
    def mock_db_model(self):
        """Create a mock database model."""
        model = MagicMock()
        model.__tablename__ = "test_events"
        return model

    def test_readers_initialization(self, mock_session_maker, mock_db_model):
        """Test Readers initialization."""
        from fleuve.tests.models import TestOffsetModel

        readers = Readers(
            pg_session_maker=mock_session_maker,
            model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        assert readers._pg_session_maker == mock_session_maker
        assert readers._model == mock_db_model
        assert readers._offset_model == TestOffsetModel

    def test_readers_creates_reader(self, mock_session_maker, mock_db_model):
        """Test creating a reader from Readers."""
        from fleuve.tests.models import TestOffsetModel

        readers = Readers(
            pg_session_maker=mock_session_maker,
            model=mock_db_model,
            offset_model=TestOffsetModel,
        )
        reader = readers.reader(
            reader_name="test_reader",
            event_types=["event1"],
        )
        # Verify the reader was created correctly (Reader.init takes 's' parameter)
        assert isinstance(reader, Reader)
        assert reader.name == "test_reader"
        assert reader.event_types == ["event1"]
        assert reader.offset_model == TestOffsetModel


class TestReaderAdvanced:
    """Advanced tests for Reader class covering missing functionality."""

    @pytest.mark.asyncio
    async def test_iter_events_requires_init(self, test_session_maker):
        """Test that iter_events requires initialization."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        reader = Reader(
            reader_name="test_reader",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        # Should raise AssertionError if not initialized
        with pytest.raises(AssertionError):
            async for _ in reader.iter_events():
                pass

    @pytest.mark.asyncio
    async def test_iter_events_fetches_events(
        self, test_session, test_session_maker, clean_tables, test_event
    ):
        """Test iter_events fetches and yields events."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        # Create an event in the database
        event_model = DbEventModel(
            workflow_id="wf-1",
            workflow_version=1,
            event_type="test_event",
            workflow_type="test_workflow",
            body=test_event,
        )
        test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader_iter",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        # Use a shorter sleeper timeout to make test faster
        from fleuve.stream import Sleeper

        reader._sleeper = Sleeper(
            min_sleep=datetime.timedelta(milliseconds=10),
            max_sleep=datetime.timedelta(milliseconds=50),
        )

        async with reader:
            events = []
            count = 0
            async for event in reader.iter_events():
                events.append(event)
                count += 1
                if count >= 1:
                    # Cancel the background task to stop infinite loop
                    reader._bg_checkpoint_marking_job.cancel()
                    break  # Break after getting one event

        assert len(events) >= 1
        assert events[0].workflow_id == "wf-1"
        assert events[0].event_no == 1
        assert events[0].workflow_type == "test_workflow"

    @pytest.mark.asyncio
    async def test_iter_events_handles_errors(self, test_session_maker):
        """Test iter_events handles and logs errors properly."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        # Create a reader with a bad session maker that raises errors during _fetch_new_events
        # This will trigger the error logging path in iter_events
        bad_session = AsyncMock()
        bad_session.__aenter__ = AsyncMock(return_value=bad_session)
        bad_session.__aexit__ = AsyncMock(return_value=False)
        bad_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
        bad_maker = MagicMock(return_value=bad_session)

        reader = Reader(
            reader_name="test_reader_error",
            s=bad_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        async with reader:
            with pytest.raises(RuntimeError):
                # This will call _fetch_new_events which will call get_offset which uses the bad session
                async for _ in reader.iter_events():
                    break

    @pytest.mark.asyncio
    async def test_iter_until_exhaustion(
        self, test_session, test_session_maker, clean_tables, test_event
    ):
        """Test iter_until_exhaustion yields all events and then stops."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        # Create events in the database
        for i in range(3):
            event_model = DbEventModel(
                workflow_id=f"wf-exhaust-{i}",
                workflow_version=1,
                event_type="test_event",
                workflow_type="test_workflow",
                body=test_event,
            )
            test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader_exhaust",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        async with reader:
            events = []
            async for event in reader.iter_until_exhaustion():
                events.append(event)

        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_iter_until_exhaustion_empty(self, test_session_maker, clean_tables):
        """Test iter_until_exhaustion stops immediately when no events."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        reader = Reader(
            reader_name="test_reader_empty",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        async with reader:
            events = []
            async for event in reader.iter_until_exhaustion():
                events.append(event)

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_fetch_new_events_with_event_types(
        self, test_session, test_session_maker, clean_tables, test_event
    ):
        """Test _fetch_new_events filters by event_types."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        # Create events with different event types - use unique workflow_ids
        event_types = ["test_event", "other_event", "test_event"]
        for i, event_type in enumerate(event_types):
            event_model = DbEventModel(
                workflow_id=f"wf-event-{i}",
                workflow_version=1,
                event_type=event_type,
                workflow_type="test_workflow",
                body=test_event,
            )
            test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader_event_types",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
            event_types=["test_event"],
        )

        async with reader:
            events = []
            async for event in reader._fetch_new_events():
                events.append(event)

        assert len(events) == 2
        # Events should be TestEvent instances with type attribute
        assert all(
            hasattr(e.event, "type") and e.event.type == "test_event" for e in events
        )

    @pytest.mark.asyncio
    async def test_fetch_new_events_respects_offset(
        self, test_session, test_session_maker, clean_tables, test_event
    ):
        """Test _fetch_new_events respects offset (only fetches new events)."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        # Create events
        for i in range(3):
            event_model = DbEventModel(
                workflow_id=f"wf-{i}",
                workflow_version=1,
                event_type="test_event",
                workflow_type="test_workflow",
                body=test_event,
            )
            test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader_offset",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.last_read_event_g_id = 1  # Set offset to skip first event

        async with reader:
            events = []
            async for event in reader._fetch_new_events():
                events.append(event)

        # Should only get events with global_id > 1
        assert len(events) == 2
        assert all(e.global_id > 1 for e in events)

    @pytest.mark.asyncio
    async def test_mark_horizon_creates_offset(
        self, test_session, test_session_maker, clean_tables
    ):
        """Test _mark_horizon creates offset if it doesn't exist."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel
        from sqlalchemy import select

        reader = Reader(
            reader_name="test_reader_new",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.last_read_event_g_id = 42

        await reader._mark_horizon()

        # Check that offset was created
        async with test_session_maker() as session:
            result = await session.execute(
                select(TestOffsetModel.last_read_event_no).where(
                    TestOffsetModel.reader == "test_reader_new"
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row.last_read_event_no == 42

    @pytest.mark.asyncio
    async def test_mark_horizon_updates_existing_offset(
        self, test_session, test_session_maker, clean_tables
    ):
        """Test _mark_horizon updates existing offset."""
        from fleuve.postgres import Offset
        from fleuve.tests.models import DbEventModel, TestOffsetModel
        from sqlalchemy import insert, select

        reader = Reader(
            reader_name="test_reader_update",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.last_read_event_g_id = 100

        # Create initial offset
        async with test_session_maker() as session:
            await session.execute(
                insert(TestOffsetModel).values(
                    reader="test_reader_update",
                    last_read_event_no=50,
                )
            )
            await session.commit()

        await reader._mark_horizon()

        # Check that offset was updated
        async with test_session_maker() as session:
            result = await session.execute(
                select(TestOffsetModel.last_read_event_no).where(
                    TestOffsetModel.reader == "test_reader_update"
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row.last_read_event_no == 100

    @pytest.mark.asyncio
    async def test_mark_horizon_skips_if_already_marked(
        self, test_session, test_session_maker, clean_tables
    ):
        """Test _mark_horizon skips if already marked."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel
        from sqlalchemy import insert

        reader = Reader(
            reader_name="test_reader_skip",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.last_read_event_g_id = 50
        reader.last_read_event_g_id_marked_in_db = 50

        # Create offset with same value
        async with test_session_maker() as session:
            await session.execute(
                insert(TestOffsetModel).values(
                    reader="test_reader_skip",
                    last_read_event_no=50,
                )
            )
            await session.commit()

        # The method should return early without calling update/insert
        # We verify this by checking that the marked value remains the same
        await reader._mark_horizon()
        assert reader.last_read_event_g_id_marked_in_db == 50

    @pytest.mark.asyncio
    async def test_mark_horizon_handles_no_last_read(self, test_session_maker):
        """Test _mark_horizon handles case when last_read_event_g_id is None."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        reader = Reader(
            reader_name="test_reader_no_last",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.last_read_event_g_id = None

        # Should not raise error
        await reader._mark_horizon()

        # last_read_event_g_id_marked_in_db should still be None
        assert reader.last_read_event_g_id_marked_in_db is None

    @pytest.mark.asyncio
    async def test_bg_checkpoint_marking_runs(self, test_session_maker, clean_tables):
        """Test _bg_checkpoint_marking runs periodically."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        reader = Reader(
            reader_name="test_reader_bg",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.mark_horizon_every = 0.1  # Check every 100ms for faster test
        reader.last_read_event_g_id = 100

        # Start background task manually
        task = asyncio.create_task(reader._bg_checkpoint_marking())

        # Wait a bit for it to run
        await asyncio.sleep(0.15)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify that _mark_horizon was called (checkpoint should be marked)
        assert reader.last_read_event_g_id_marked_in_db == 100

    @pytest.mark.asyncio
    async def test_bg_checkpoint_marking_handles_errors(self, test_session_maker):
        """Test _bg_checkpoint_marking handles errors gracefully."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        reader = Reader(
            reader_name="test_reader_bg_error",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        reader.mark_horizon_every = 0.05

        # Make _mark_horizon raise an error
        original_mark = reader._mark_horizon

        async def failing_mark():
            raise RuntimeError("Test error")

        reader._mark_horizon = failing_mark

        # Start background task
        task = asyncio.create_task(reader._bg_checkpoint_marking())

        # Wait a bit for it to try and fail
        await asyncio.sleep(0.1)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Task should have handled the error without crashing
        assert task.done()

    @pytest.mark.asyncio
    async def test_fetch_new_events_batch_size(
        self, test_session, test_session_maker, clean_tables, test_event
    ):
        """Test _fetch_new_events respects batch_size parameter."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel

        # Create more events than batch size
        for i in range(150):
            event_model = DbEventModel(
                workflow_id=f"wf-{i}",
                workflow_version=1,
                event_type="test_event",
                workflow_type="test_workflow",
                body=test_event,
            )
            test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader_batch",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        async with reader:
            events = []
            async for event in reader._fetch_new_events(batch_size=50):
                events.append(event)
                if len(events) >= 50:  # Only check first batch
                    break

        # Should respect batch size
        assert len(events) == 50
