import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import get_settings
from routers import checkin, dailysync, journeys, strava, workout


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()  # fails fast on missing configuration
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not settings.allowed_ids:
        logging.getLogger(__name__).warning(
            "ALLOWED_USER_IDS is empty: every account that can sign in may use this backend"
        )
    yield


app = FastAPI(title="Virtual Coach", lifespan=lifespan)


@app.get("/")
def read_root():
    return {"status": "Virtual Coach Backend is Running 🚀"}


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(journeys.router)
app.include_router(dailysync.router)
app.include_router(workout.router)
app.include_router(strava.router)
app.include_router(checkin.router)
