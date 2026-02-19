"""
Utilities for action execution, including background condition checks.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def run_with_background_check(
    gen: AsyncIterator[T],
    condition: Callable[[], Awaitable[bool]],
    interval: float = 1.0,
    on_stop_cmd: T | None = None,
) -> AsyncIterator[T]:
    """
    Wrap an async generator; run condition in background. When it returns True,
    stop consuming and optionally yield on_stop_cmd before returning.

    Args:
        gen: The inner async generator (items to yield).
        condition: Async callable returning True when the action should stop.
        interval: Seconds between condition checks.
        on_stop_cmd: Optional command to yield when stopping due to condition.

    Example:
        async def act_on(self, event, context):
            async def items():
                for x in self._fetch():
                    yield ProcessCmd(x)

            async for item in run_with_background_check(
                items(),
                condition=lambda: self._is_order_cancelled(event),
                interval=1.0,
                on_stop_cmd=CmdActionStopped(reason="order cancelled"),
            ):
                yield item
    """
    stop_event = asyncio.Event()

    async def checker() -> None:
        while not stop_event.is_set():
            try:
                if await condition():
                    stop_event.set()
                    return
            except Exception as e:
                logger.warning("Background check condition raised, continuing: %s", e)
            await asyncio.sleep(interval)

    checker_task = asyncio.create_task(checker())
    try:
        async for item in gen:
            if stop_event.is_set():
                if on_stop_cmd is not None:
                    yield on_stop_cmd
                return
            yield item
    finally:
        stop_event.set()
        checker_task.cancel()
        try:
            await checker_task
        except asyncio.CancelledError:
            pass
