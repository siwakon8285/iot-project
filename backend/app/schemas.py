"""Pydantic schemas for the AI Smart Room API."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool


RoomStatus = Literal["GOOD", "MODERATE", "HOT"]


class Reading(BaseModel):
    """Sensor data kept in the existing response data shape."""

    device_id: str = Field(..., min_length=1)
    temperature: float
    humidity: float = Field(..., ge=0, le=100)
    co2: Optional[float] = None
    fan_on: StrictBool


class ReadingRequest(Reading):
    """A sensor reading accepted from an ESP32 device."""

    status: Optional[RoomStatus] = None


class ReadingResponse(BaseModel):
    """The API response returned after accepting a reading."""

    success: bool
    status: str
    recommendation: str
    data: Reading


class ReadingHistoryItem(BaseModel):
    """A persisted reading returned by the history endpoint."""

    id: int
    device_id: str
    temperature: float
    humidity: float
    co2: Optional[float] = None
    fan_on: StrictBool
    status: RoomStatus
    recommendation: str
    created_at: datetime


Sensitivity = Literal[
    "heat_sensitive",
    "cold_sensitive",
    "high_humidity_sensitive",
    "dry_air_sensitive",
    "poor_ventilation_sensitive",
    "respiratory_sensitive",
]
Suitability = Literal["SUITABLE", "CAUTION", "NOT_SUITABLE"]


class AssessmentRequest(BaseModel):
    """Temporary preferences; these are never persisted."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, max_length=255)
    sensitivities: list[Sensitivity] = Field(..., min_length=1)


class AssessmentEnvironment(BaseModel):
    temperature: float
    humidity: float
    co2: Optional[float]
    status: RoomStatus


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suitability: Suitability
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    reasons: list[str] = Field(..., min_length=1, max_length=4)
    recommendations: list[str] = Field(..., min_length=1, max_length=4)


class AssessmentResponse(BaseModel):
    success: bool
    source: Literal["groq", "fallback"]
    device_id: str
    profile: list[Sensitivity]
    environment: AssessmentEnvironment
    assessment: Assessment
    disclaimer: str
