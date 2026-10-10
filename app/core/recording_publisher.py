"""Bound best-effort recording publication without blocking the ASGI loop."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="recording-publish")
_slots = asyncio.Semaphore(2)


def _publish(task, payload):
    # Disable publish retries; the middleware already records failures.
    with task.app.connection_for_write() as connection:
        connection.connect_timeout = settings.RECORDING_PUBLISH_TIMEOUT_SECONDS
        task.apply_async(args=(payload,), connection=connection, retry=False)


async def publish_recording(task, payload):
    # Keep the pool bounded even when a broker call ignores its socket timeout.
    if _slots.locked():
        raise RuntimeError("流量录制发布队列已满")
    await _slots.acquire()
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_executor, _publish, task, payload)
    def completed(done):
        _slots.release()
        # Retrieve late failures too (after the caller timed out), avoiding an
        # unhandled-future warning with potentially sensitive broker details.
        if not done.cancelled():
            done.exception()
    future.add_done_callback(completed)
    await asyncio.wait_for(
        asyncio.shield(future), settings.RECORDING_PUBLISH_TIMEOUT_SECONDS
    )
