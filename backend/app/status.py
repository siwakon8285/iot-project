"""Configured room-status and environmental recommendation rules."""

from typing import Dict, List, Optional

from .schemas import RoomStatus


# These are project-configured prototype thresholds, not universal medical standards.
CO2_MODERATE_PPM = 1000
CO2_HOT_PPM = 1500
TEMPERATURE_MODERATE_C = 28
TEMPERATURE_HOT_C = 30
HUMIDITY_MODERATE_PERCENT = 70
HUMIDITY_HOT_PERCENT = 85

_FACTOR_LABELS = {
    "co2": "CO2",
    "temperature": "room temperature",
    "humidity": "humidity",
}


def _level(value: Optional[float], moderate: float, hot: float) -> RoomStatus:
    """Classify one measurement using the configured thresholds."""

    if value is None:
        return "GOOD"
    if value >= hot:
        return "HOT"
    if value >= moderate:
        return "MODERATE"
    return "GOOD"


def _measurement_levels(
    temperature: float,
    humidity: float,
    co2: Optional[float],
) -> Dict[str, RoomStatus]:
    """Return the configured level for each available environmental factor."""

    return {
        "co2": _level(co2, CO2_MODERATE_PPM, CO2_HOT_PPM),
        "temperature": _level(
            temperature,
            TEMPERATURE_MODERATE_C,
            TEMPERATURE_HOT_C,
        ),
        "humidity": _level(
            humidity,
            HUMIDITY_MODERATE_PERCENT,
            HUMIDITY_HOT_PERCENT,
        ),
    }


def determine_status(
    temperature: float,
    humidity: float,
    co2: Optional[float] = None,
) -> RoomStatus:
    """Calculate fallback status from all available environmental measurements."""

    levels = _measurement_levels(temperature, humidity, co2)
    if any(level == "HOT" for level in levels.values()):
        return "HOT"
    if any(level == "MODERATE" for level in levels.values()):
        return "MODERATE"
    return "GOOD"


def derive_status(
    temperature: float,
    humidity: float,
    co2: Optional[float] = None,
) -> RoomStatus:
    """Backward-compatible name for the configured fallback status calculation."""

    return determine_status(temperature, humidity, co2)


def resolve_status(
    temperature: float,
    humidity: float,
    reported_status: Optional[RoomStatus],
    co2: Optional[float] = None,
) -> RoomStatus:
    """Use a valid device status as authoritative, otherwise use the fallback."""

    if reported_status is not None:
        return reported_status
    return determine_status(temperature, humidity, co2)


def _join(items: List[str]) -> str:
    """Join short phrases with natural punctuation."""

    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _single_factor_recommendation(factor: str, level: RoomStatus) -> str:
    """Return the concise recommendation for one elevated factor."""

    if factor == "co2":
        if level == "HOT":
            return (
                "CO2 is high. Increase fresh-air ventilation and check room airflow. "
                "Maintaining good ventilation is especially important in rooms used "
                "by older adults or people with respiratory sensitivity."
            )
        return "CO2 is elevated. Improve ventilation and continue monitoring the room."

    if factor == "temperature":
        if level == "HOT":
            return (
                "Room temperature is high. Improve cooling or air circulation and "
                "continue monitoring patient comfort."
            )
        return (
            "Room temperature is above the configured comfort range. Consider "
            "improving air circulation or cooling."
        )

    if level == "HOT":
        return (
            "Humidity is high. Improve ventilation or dehumidification to maintain "
            "a more comfortable room environment."
        )
    return "Humidity is elevated. Improve airflow and continue monitoring the room."


def _multiple_factor_recommendation(
    factors: List[str],
    levels: Dict[str, RoomStatus],
) -> str:
    """Mention multiple elevated factors and pair them with practical actions."""

    labels = [_FACTOR_LABELS[factor] for factor in factors]
    if all(levels[factor] == "HOT" for factor in factors):
        issue = f"{_join(labels)} are high"
    else:
        issue_parts = []
        for factor in factors:
            label = _FACTOR_LABELS[factor]
            if factor == "temperature" and levels[factor] == "MODERATE":
                issue_parts.append(
                    "room temperature is above the configured comfort range"
                )
            else:
                adjective = "high" if levels[factor] == "HOT" else "elevated"
                issue_parts.append(f"{label} is {adjective}")
        issue = _join(issue_parts)

    actions = []
    for factor in factors:
        if factor == "co2":
            actions.append(
                "increase fresh-air ventilation"
                if levels[factor] == "HOT"
                else "improve ventilation"
            )
        elif factor == "temperature":
            actions.append(
                "improve cooling or air circulation"
                if levels[factor] == "HOT"
                else "consider improving air circulation or cooling"
            )
        else:
            actions.append(
                "reduce excess humidity"
                if levels[factor] == "HOT"
                else "improve airflow"
            )

    action_text = _join(actions)
    issue = f"{issue[0].upper()}{issue[1:]}"
    return f"{issue}. {action_text[0].upper()}{action_text[1:]}."


def generate_recommendation(
    temperature: float,
    humidity: float,
    co2: Optional[float] = None,
) -> str:
    """Generate deterministic environmental guidance from the actual values."""

    levels = _measurement_levels(temperature, humidity, co2)
    elevated_factors = [
        factor
        for factor in ("co2", "temperature", "humidity")
        if levels[factor] != "GOOD"
    ]

    if not elevated_factors:
        return "Room conditions are within the configured comfort range. Continue monitoring."
    if len(elevated_factors) == 1:
        factor = elevated_factors[0]
        return _single_factor_recommendation(factor, levels[factor])
    return _multiple_factor_recommendation(elevated_factors, levels)
