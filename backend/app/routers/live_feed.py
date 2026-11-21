from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user
from ..live_feed import live_feed


router = APIRouter(prefix="/api/live-feed", tags=["live feed"])


@router.get("/status")
def status(_: dict = Depends(current_user)):
    return live_feed.status()


@router.post("/start")
def start(_: dict = Depends(current_user)):
    try:
        return live_feed.start()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/stop")
def stop(_: dict = Depends(current_user)):
    return live_feed.stop()
