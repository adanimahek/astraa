import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import settings
from . import auth, db
from .live_feed import live_feed as live_feed_manager
from .routers import detect, live_feed as live_feed_router, simulation


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.ping()
    auth.seed_admin()
    from .yolo_service import model
    model()
    try:
        yield
    finally:
        live_feed_manager.stop()


os.makedirs(settings.results_dir, exist_ok=True)
app = FastAPI(title="ASTRA API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/results", StaticFiles(directory=settings.results_dir), name="results")
app.include_router(auth.router)
app.include_router(detect.router)
app.include_router(live_feed_router.router)
app.include_router(simulation.router)

@app.get("/api/health")
def health():
    return {"status": "ok"}
