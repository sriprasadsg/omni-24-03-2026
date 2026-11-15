"""lock_with_renewal lets a cancellation through while it leaves its block.

A loop that holds the lock is cancelled at shutdown. When the cancellation landed while the context manager
was waiting for its renew task to end, it was swallowed: the loop went on running and the event loop could
never close (a backend shutdown, or a test's app teardown, waited forever).
"""
import asyncio

import pytest

import distributed_lock


@pytest.fixture
def slow_renewal(monkeypatch):
    """A lock whose renewal is on the wire and takes a moment to give up once cancelled. Returns the event
    set when the renew task has been cancelled (the lock's exit is then waiting for it) and the release calls."""
    leaving = asyncio.Event()
    released: list = []

    async def acquire(db, name, ttl):
        return "token"

    async def renew(db, name, token, ttl):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            leaving.set()
            await asyncio.sleep(0.2)
            raise
        return True

    async def release(db, name, token):
        released.append((name, token))

    monkeypatch.setattr(distributed_lock, "acquire_lock", acquire)
    monkeypatch.setattr(distributed_lock, "renew_lock", renew)
    monkeypatch.setattr(distributed_lock, "release_lock", release)
    return leaving, released


async def _loop(passes: list) -> None:
    while True:
        async with distributed_lock.lock_with_renewal(None, "job", ttl_seconds=30, renew_every=0.01):
            await asyncio.sleep(0.05)
        passes.append(1)
        await asyncio.sleep(0.3)


@pytest.mark.asyncio
async def test_a_cancellation_during_the_exit_stops_the_loop_and_releases_the_lock(slow_renewal):
    leaving, released = slow_renewal
    passes: list = []
    task = asyncio.create_task(_loop(passes))
    await asyncio.wait_for(leaving.wait(), 5)        # the loop is in the lock's exit, waiting for the renew task
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=2)
    if not done:                                     # the old behaviour: tidy up so the test itself can end
        task.cancel()
        await asyncio.wait({task}, timeout=2)
    assert done, "the cancellation was swallowed and the loop went on"
    assert task.cancelled()
    assert passes == []
    assert released == [("job", "token")]


@pytest.mark.asyncio
async def test_an_uncancelled_exit_still_ends_normally_and_releases_once(slow_renewal):
    _, released = slow_renewal
    async with distributed_lock.lock_with_renewal(None, "job", ttl_seconds=30, renew_every=0.01) as handle:
        assert handle.acquired is True
        await asyncio.sleep(0.05)
    assert released == [("job", "token")]
