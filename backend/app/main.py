"""FastAPI application for AI Smart Health Environment."""

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import crud
from .ai_assessment import RECENT_WINDOW, assess_environment
from .database import get_db
from .schemas import (
    AssessmentRequest,
    AssessmentResponse,
    ReadingHistoryItem,
    ReadingRequest,
    ReadingResponse,
)
from .status import generate_recommendation, resolve_status


app = FastAPI(
    title="AI Smart Health Environment API",
    description="Environmental telemetry and personalized AI assessment API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple service health check."""

    return {"status": "ok"}


@app.post("/api/v1/readings", response_model=ReadingResponse)
def create_reading(
    reading: ReadingRequest,
    db: Session = Depends(get_db),
) -> ReadingResponse:
    """Accept, classify, and persist a sensor reading."""

    status = resolve_status(
        reading.temperature,
        reading.humidity,
        reading.status,
        co2=reading.co2,
    )
    recommendation = generate_recommendation(
        reading.temperature,
        reading.humidity,
        reading.co2,
    )
    try:
        db_reading = crud.create_sensor_reading(db, reading, status, recommendation)
        db.commit()
        db.refresh(db_reading)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Unable to save reading to the database",
        ) from exc

    return crud.to_reading_response(db_reading)


@app.get("/api/v1/readings/latest", response_model=ReadingResponse)
def get_latest_reading(db: Session = Depends(get_db)) -> ReadingResponse:
    """Return the latest persisted reading, if one has been received."""

    try:
        db_reading = crud.get_latest_reading(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to read from the database",
        ) from exc

    if db_reading is None:
        raise HTTPException(status_code=404, detail="No readings available yet")
    return crud.to_reading_response(db_reading)


@app.get("/api/v1/readings", response_model=list[ReadingHistoryItem])
def list_readings(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ReadingHistoryItem]:
    """Return persisted readings newest first."""

    try:
        readings = crud.get_readings(db, limit)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to read from the database",
        ) from exc
    return [crud.to_history_item(reading) for reading in readings]


@app.post("/api/v1/ai/assessment", response_model=AssessmentResponse)
def create_ai_assessment(
    request: AssessmentRequest,
    db: Session = Depends(get_db),
) -> AssessmentResponse:
    """Interpret one device's persisted readings for temporary preferences."""

    try:
        readings = crud.get_recent_readings_for_device(db, request.device_id, RECENT_WINDOW)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to read from the database",
        ) from exc

    if not readings:
        raise HTTPException(status_code=404, detail="No readings available for device")
    return assess_environment(request, readings)
