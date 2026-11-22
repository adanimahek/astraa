import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import settings
from . import auth, db
from .live_feed import live_feed as live_feed_manager
from .routers import (challans as challans_router, detect, enforcement_dashboard,
                      live_feed as live_feed_router, owner as owner_router,
                      registry as registry_router, simulation, violations)
from .enforcement import challans as enforcement_challans, registry as enforcement_registry, store as enforcement_store
from .enforcement.config import enforcement_settings
from .enforcement import payments as enforcement_payments


async def _overdue_loop():
    """FR15: periodically flag unpaid challans that are past their due date."""
    while True:
        try:
            await asyncio.to_thread(enforcement_payments.mark_overdue)
        except Exception:  # keep the loop alive; Atlas hiccups are retried next cycle
            logging.getLogger("astra.enforcement").exception("Overdue check failed")
        await asyncio.sleep(max(1, enforcement_settings.overdue_check_minutes) * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.ping()
    auth.seed_admin()
    enforcement_store.ensure_indexes()
    enforcement_registry.ensure_indexes()
    enforcement_challans.ensure_indexes()
    from .yolo_service import model
    model()
    overdue_task = asyncio.create_task(_overdue_loop())
    try:
        yield
    finally:
        overdue_task.cancel()
        live_feed_manager.stop()


os.makedirs(settings.results_dir, exist_ok=True)
os.makedirs(enforcement_settings.evidence_dir, exist_ok=True)
app = FastAPI(title="ASTRA API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/results", StaticFiles(directory=settings.results_dir), name="results")
app.include_router(auth.router)
app.include_router(detect.router)
app.include_router(live_feed_router.router)
app.include_router(simulation.router)
app.include_router(violations.router)
app.include_router(registry_router.router)
app.include_router(challans_router.router)
app.include_router(owner_router.router)
app.include_router(enforcement_dashboard.router)

@app.get("/api/health")
def health():
    return {"status": "ok"}
