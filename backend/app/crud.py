"""Small database operations used by the API routes."""

from typing import Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from .models import SensorReading
from .schemas import Reading, ReadingHistoryItem, ReadingRequest, ReadingResponse


def create_sensor_reading(
    db: Session,
    reading: ReadingRequest,
    status: str,
    recommendation: str,
) -> SensorReading:
    """Add a reading to the current transaction without committing it."""

    db_reading = SensorReading(
        device_id=reading.device_id,
        temperature=reading.temperature,
        humidity=reading.humidity,
        co2=reading.co2,
        fan_on=reading.fan_on,
        status=status,
        recommendation=recommendation,
    )
    db.add(db_reading)
    return db_reading


def get_latest_reading(db: Session) -> Optional[SensorReading]:
    """Return the newest reading, using the id as a deterministic tie-breaker."""

    statement: Select[tuple[SensorReading]] = (
        select(SensorReading)
        .order_by(SensorReading.created_at.desc(), SensorReading.id.desc())
        .limit(1)
    )
    return db.scalar(statement)


def get_readings(db: Session, limit: int) -> list[SensorReading]:
    """Return persisted readings newest first."""

    statement: Select[tuple[SensorReading]] = (
        select(SensorReading)
        .order_by(SensorReading.created_at.desc(), SensorReading.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_recent_readings_for_device(
    db: Session, device_id: str, limit: int
) -> list[SensorReading]:
    """Read one device's newest persisted readings without changing telemetry."""

    statement: Select[tuple[SensorReading]] = (
        select(SensorReading)
        .where(SensorReading.device_id == device_id)
        .order_by(SensorReading.created_at.desc(), SensorReading.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def to_reading_response(db_reading: SensorReading) -> ReadingResponse:
    """Convert a database row to the existing single-reading API response."""

    return ReadingResponse(
        success=True,
        status=db_reading.status,
        recommendation=db_reading.recommendation,
        data=Reading(
            device_id=db_reading.device_id,
            temperature=db_reading.temperature,
            humidity=db_reading.humidity,
            co2=db_reading.co2,
            fan_on=db_reading.fan_on,
        ),
    )


def to_history_item(db_reading: SensorReading) -> ReadingHistoryItem:
    """Convert a database row to the history response schema."""

    return ReadingHistoryItem(
        id=db_reading.id,
        device_id=db_reading.device_id,
        temperature=db_reading.temperature,
        humidity=db_reading.humidity,
        co2=db_reading.co2,
        fan_on=db_reading.fan_on,
        status=db_reading.status,
        recommendation=db_reading.recommendation,
        created_at=db_reading.created_at,
    )
