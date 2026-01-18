from fastapi import FastAPI
from routers import journeys, dailysync, workout, strava, checkin

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Virtual Coach Backend is Running 🚀"}

app.include_router(journeys.router)
app.include_router(dailysync.router)
app.include_router(workout.router)
app.include_router(strava.router)
app.include_router(checkin.router)