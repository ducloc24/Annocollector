"""Periodic maintenance that must not depend on someone opening a page."""

import asyncio
import logging

from app.core.clock import utcnow
from app.db.session import SessionLocal
from app.repositories.ops import OpsRepository

logger = logging.getLogger(__name__)

LEASE_SWEEP_SECONDS = 300


async def sweep_expired_leases() -> int:
    """Return jobs whose lease ran out to the pool; returns how many."""
    async with SessionLocal() as session:
        released = await OpsRepository(session).release_all_expired_leases(utcnow())
        await session.commit()
    return released


async def lease_sweeper(interval: int = LEASE_SWEEP_SECONDS) -> None:
    while True:
        try:
            released = await sweep_expired_leases()
            if released:
                logger.info("Released %s job(s) with expired leases", released)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the loop alive across database hiccups
            logger.exception("Lease sweep failed")
        await asyncio.sleep(interval)
