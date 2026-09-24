"""Reserved Row API -- the HTTP layer over the booking service and the Phase 4
nudge engine. The React frontend in web/ is the only client.

    uvicorn main:app --reload          # dev (run from api/)
    python -m uvicorn main:app         # serves web/dist too if it's built

Everything stateful lives on app.state: one BookingService (shared SQLite +
JSONL) and one long-lived NudgeEngine, primed from the event log on startup and
ticked (under a lock) on every /api/floor read and every SSE push.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import _bootstrap
import config
from members import DEFAULT_MEMBERS, member_by_id
from models import reserved_machines
from service import BookingError, build_service

from nudge_engine import NudgeEngine, adherence_stats
from occupancy import OccupancyTracker, read_state_log, write_state_change

import schemas
from slots import gym_tz, slot_grid
from verdict import machine_view, pick_booking, read_events

EVENT_LABELS = {
    "booking_created": "booked",
    "booking_cancelled": "cancelled",
    "booking_rejected": "booking rejected",
    "no_show_released": "no-show released",
    "nudge_fired": "nudge fired",
}


def _name(member_id: str) -> str:
    m = member_by_id(member_id)
    return m.name if m else member_id


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    svc = build_service(
        db_path=_bootstrap.DB_PATH,
        event_log_path=_bootstrap.EVENT_LOG_PATH,
        check_same_thread=False,
    )
    engine = NudgeEngine(svc)
    engine.prime_from_events(read_events(_bootstrap.EVENT_LOG_PATH))
    app.state.svc = svc
    app.state.engine = engine
    app.state.lock = asyncio.Lock()
    yield


app = FastAPI(title="Reserved Row API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------- member: booking
@app.get("/api/members", response_model=list[schemas.Member])
def members():
    return [schemas.Member(id=m.id, name=m.name, is_premium=m.is_premium)
            for m in DEFAULT_MEMBERS]


@app.get("/api/machines", response_model=list[schemas.Machine])
def machines(request: Request):
    return [schemas.Machine(id=m.id, name=m.name)
            for m in reserved_machines(request.app.state.svc.machines)]


@app.get("/api/slots", response_model=list[schemas.SlotRow])
def slots(request: Request, member_id: str | None = None, day: str = "today"):
    tz = gym_tz()
    target = date.today() + (timedelta(days=1) if day == "tomorrow" else timedelta())
    rows = slot_grid(
        request.app.state.svc, target, member_id,
        datetime.now(timezone.utc), tz, member_name=_name,
    )
    return rows


def _booking_out(b) -> schemas.BookingOut:
    return schemas.BookingOut(
        id=b.id, machine_id=b.machine_id, member_id=b.member_id,
        member_name=_name(b.member_id), start=b.start, end=b.end, status=b.status.value,
    )


@app.post("/api/bookings", response_model=schemas.BookingOut, status_code=201)
def create_booking(request: Request, body: schemas.CreateBooking):
    try:
        b = request.app.state.svc.create_booking(
            body.machine_id, body.member_id, body.start, body.end
        )
    except BookingError as exc:
        raise HTTPException(
            409, detail={"code": getattr(exc, "code", "booking_error"), "message": str(exc)}
        )
    return _booking_out(b)


@app.delete("/api/bookings/{booking_id}", response_model=schemas.BookingOut)
def cancel_booking(request: Request, booking_id: str):
    try:
        b = request.app.state.svc.cancel_booking(booking_id)
    except BookingError as exc:
        raise HTTPException(404, detail={"code": getattr(exc, "code", "unknown_booking"),
                                        "message": str(exc)})
    return _booking_out(b)


@app.post("/api/bookings/suggest", response_model=schemas.Suggestion)
def suggest(request: Request, body: schemas.SuggestRequest):
    s = request.app.state.svc.suggest_slot(
        timedelta(minutes=body.duration_minutes),
        member_id=body.member_id,
        earliest_start=body.earliest,
    )
    return schemas.Suggestion(
        machine_id=s.machine_id, start=s.start, end=s.end,
        wait_seconds=s.wait.total_seconds(),
    )


# ----------------------------------------------------------------- staff: floor
async def floor_state(app: FastAPI) -> schemas.FloorState:
    svc, engine = app.state.svc, app.state.engine
    now = datetime.now(timezone.utc)

    tracker = OccupancyTracker()
    tracker.apply_all(read_state_log(_bootstrap.STATE_LOG_PATH))
    occ = tracker.machine_occupancy()

    async with app.state.lock:
        fired = engine.tick(occ, now)

    out_machines = []
    for m in reserved_machines(svc.machines):
        active = svc.bookings(machine_id=m.id, active_only=True)
        booking = pick_booking(active, now)
        since_raw = tracker.since(m.id)
        since = datetime.fromisoformat(since_raw) if since_raw else None
        mv = machine_view(
            m, booking, _name(booking.member_id) if booking else None,
            occ.get(m.id), since, now,
            grace=config.GRACE_PERIOD, nudge_window=config.NUDGE_WINDOW,
        )
        out_machines.append(schemas.FloorMachine(
            machine_id=mv.machine_id, machine_name=mv.machine_name,
            member_name=mv.member_name,
            window=[mv.window[0], mv.window[1]] if mv.window else None,
            camera=schemas.CameraState(occupied=mv.occupied, since=mv.occupied_since),
            verdict=mv.verdict, headline=mv.headline,
        ))

    stats = adherence_stats(svc, now)
    return schemas.FloorState(
        now=now,
        scheduler_mode=config.SCHEDULER_MODE,
        machines=out_machines,
        adherence=schemas.Adherence(**stats.to_dict()),
        fired=[schemas.FiredEvent(kind=e.kind, machine_id=e.machine_id,
                                  member_name=_name(e.member_id), detail=e.detail)
               for e in fired],
    )


@app.get("/api/floor", response_model=schemas.FloorState)
async def floor(request: Request):
    return await floor_state(request.app)


@app.get("/api/activity", response_model=list[schemas.ActivityEvent])
def activity(request: Request, limit: int = 15):
    out = []
    for ev in read_events(_bootstrap.EVENT_LOG_PATH, limit=limit):
        data = ev.get("data", {})
        out.append(schemas.ActivityEvent(
            at=ev["at"],
            type=ev["type"],
            label=EVENT_LABELS.get(ev["type"], ev["type"]),
            machine_id=data.get("machine_id"),
            member_name=_name(data["member_id"]) if data.get("member_id") else None,
        ))
    out.reverse()
    return out


@app.post("/api/sim/occupancy", response_model=schemas.CameraState)
def sim_occupancy(body: schemas.SimOccupancy):
    rec = write_state_change(
        _bootstrap.STATE_LOG_PATH, body.machine_id, body.occupied,
        datetime.now(timezone.utc),
    )
    return schemas.CameraState(occupied=body.occupied, since=rec["at"])


@app.get("/api/stream")
async def stream(request: Request):
    async def gen():
        while True:
            if await request.is_disconnected():
                break
            state = await floor_state(request.app)
            yield f"data: {state.model_dump_json()}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ----------------------------------------------------------- serve the built SPA
if _bootstrap.WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_bootstrap.WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = _bootstrap.WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_bootstrap.WEB_DIST / "index.html")
