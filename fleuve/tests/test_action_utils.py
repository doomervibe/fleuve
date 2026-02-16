"""
Unit tests for fleuve.action_utils module.
"""
import asyncio

import pytest

from fleuve.action_utils import run_with_background_check


class TestRunWithBackgroundCheck:
    """Tests for run_with_background_check utility."""

    @pytest.mark.asyncio
    async def test_yields_all_items_when_condition_never_met(self):
        """Test that all items are yielded when condition never returns True."""
        async def gen():
            for i in range(3):
                yield f"item-{i}"

        async def never_stop():
            return False

        result = []
        async for item in run_with_background_check(
            gen(),
            condition=never_stop,
            interval=0.01,
        ):
            result.append(item)

        assert result == ["item-0", "item-1", "item-2"]

    @pytest.mark.asyncio
    async def test_stops_and_yields_on_stop_cmd_when_condition_met(self):
        """Test that generator stops when condition is met and on_stop_cmd is yielded."""
        stop_after = [2]
        count = [0]

        async def condition():
            count[0] += 1
            return count[0] >= stop_after[0]

        async def gen():
            for i in range(10):
                yield f"item-{i}"
                await asyncio.sleep(0.02)

        result = []
        async for item in run_with_background_check(
            gen(),
            condition=condition,
            interval=0.01,
            on_stop_cmd="STOP_CMD",
        ):
            result.append(item)

        assert "item-0" in result
        assert result[-1] == "STOP_CMD"

    @pytest.mark.asyncio
    async def test_stops_without_on_stop_cmd_when_condition_met(self):
        """Test that generator stops when condition is met even without on_stop_cmd."""
        async def condition():
            await asyncio.sleep(0.05)
            return True

        async def gen():
            yield "item-0"
            await asyncio.sleep(0.02)
            yield "item-1"
            await asyncio.sleep(0.02)
            yield "item-2"

        result = []
        async for item in run_with_background_check(
            gen(),
            condition=condition,
            interval=0.01,
            on_stop_cmd=None,
        ):
            result.append(item)

        assert len(result) >= 1
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_empty_generator(self):
        """Test with empty generator."""
        async def gen():
            if False:
                yield

        async def never_stop():
            return False

        result = []
        async for item in run_with_background_check(
            gen(),
            condition=never_stop,
            interval=0.01,
        ):
            result.append(item)

        assert result == []

    @pytest.mark.asyncio
    async def test_condition_raises_logs_and_continues(self):
        """Test that when condition raises, we log and continue (don't stop action)."""
        condition_called = [0]

        async def condition():
            condition_called[0] += 1
            if condition_called[0] == 1:
                raise ValueError("condition error")
            return False

        async def gen():
            for i in range(3):
                yield f"item-{i}"
                await asyncio.sleep(0.02)

        result = []
        async for item in run_with_background_check(
            gen(),
            condition=condition,
            interval=0.01,
        ):
            result.append(item)

        assert result == ["item-0", "item-1", "item-2"]
        assert condition_called[0] >= 2
