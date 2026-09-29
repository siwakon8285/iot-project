"""Read-only, personalized interpretation of persisted environmental readings."""

import json
import logging
import re
from statistics import mean
from typing import Any, Optional

from pydantic import ValidationError

from .config import get_groq_api_key, get_groq_model
from .models import SensorReading
from .schemas import Assessment, AssessmentEnvironment, AssessmentRequest, AssessmentResponse
from .status import (
    CO2_HOT_PPM,
    CO2_MODERATE_PPM,
    HUMIDITY_HOT_PERCENT,
    HUMIDITY_MODERATE_PERCENT,
    TEMPERATURE_HOT_C,
    TEMPERATURE_MODERATE_C,
)


RECENT_WINDOW = 12
GROQ_TIMEOUT_SECONDS = 6.0
logger = logging.getLogger(__name__)
LOW_TEMPERATURE_C = 20.0  # AI comfort cue only; does not change device status.
LOW_HUMIDITY_PERCENT = 30.0  # AI comfort cue only.
SENSITIVITY_DESCRIPTIONS = {
    "heat_sensitive": "ไวต่ออากาศร้อน",
    "cold_sensitive": "ไวต่ออากาศเย็น",
    "high_humidity_sensitive": "ไวต่อความชื้นสูง",
    "dry_air_sensitive": "ไวต่ออากาศแห้ง",
    "poor_ventilation_sensitive": "ไวต่ออากาศอับ",
    "respiratory_sensitive": "ระบบทางเดินหายใจไวต่อสภาพแวดล้อม",
}
DISCLAIMER = (
    "คำแนะนำนี้อ้างอิงจากค่า CO₂ อุณหภูมิ ความชื้น และลักษณะที่คุณเลือก "
    "ไม่ใช่การวินิจฉัยทางการแพทย์"
)

SYSTEM_PROMPT = """You are an AI assistant for environmental suitability.
Analyze ONLY the supplied sensor context and selected sensitivities. The only measurements are CO₂ (ppm), temperature (°C), and relative humidity (%). Never describe CO₂ as PM, PM2.5, PM10, dust, or particulate matter. Do not infer oxygen, pollen, VOCs, or other pollutants from CO₂. Never invent a measurement or a numeric comfort threshold.
The Python-calculated latest_factor_levels determine which values may be called elevated: only MODERATE or HOT is elevated; GOOD is not. A normal temperature must not be called warm, high, overheating, or a problem because CO₂ or humidity is high. Only discuss low temperature for cold_sensitive when personalized_low_flags.temperature_low is true. Only discuss low humidity for dry_air_sensitive or respiratory_sensitive when personalized_low_flags.humidity_low is true.
Use profile_relevant_factors to prioritize actual issues. Do not force every selected sensitivity into the explanation when its associated value is normal. You may mention other elevated measurements as environmental context. Treat deterministic_status and deterministic_suitability as authoritative, but do not say status codes or threshold names in user-facing text.
Write all user-facing strings in natural, concise Thai, speaking directly and calmly to the person. Use “สภาพแวดล้อม”, not “ห้อง”. Avoid “ระบบตรวจพบ”, “ระบบประเมินว่า”, “ตามเกณฑ์ของระบบ”, “ตาม threshold”, “จากการประมวลผลของระบบ”, and technical-report language. Do not claim to be a doctor, diagnose diseases, recommend medication or treatment, or claim medical safety.
In the summary, mention only the important measured values and explain why they matter for relevant selected sensitivities. Do not list normal values as problems or repeat every normal sensor value. Give 1–3 factual reasons and 2–4 practical recommendations related to the actual issues. For elevated CO₂, suggest suitable fresh-air ventilation and rechecking CO₂; never imply ordinary air conditioning, a humidifier, or an air purifier removes CO₂. For high humidity, suggest dehumidification or suitable ventilation; never suggest a humidifier to lower humidity. For elevated temperature, suggest comfortable cooling or airflow. Do not suggest reducing the number of people without evidence.
Use these cautious Thai titles: SUITABLE="สภาพแวดล้อมตอนนี้ค่อนข้างเหมาะกับคุณ"; CAUTION="สภาพแวดล้อมตอนนี้ควรเฝ้าระวังเล็กน้อย"; NOT_SUITABLE="สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ". Keep the title short and the summary to 1–3 sentences. Do not repeat the disclaimer inside the assessment.
Sensitivity meanings: heat_sensitive=ไวต่ออากาศร้อน; cold_sensitive=ไวต่ออากาศเย็น; high_humidity_sensitive=ไวต่อความชื้นสูง; dry_air_sensitive=ไวต่ออากาศแห้ง; poor_ventilation_sensitive=ไวต่ออากาศอับ; respiratory_sensitive=ระบบทางเดินหายใจไวต่อสภาพแวดล้อม.
HOT must never be described as completely normal; GOOD must not be described as dangerous without a supported sensitivity concern. Use exactly the supplied deterministic_suitability enum value.
Respond ONLY with this JSON object structure, with no other keys or Markdown:
{"suitability":"SUITABLE|CAUTION|NOT_SUITABLE","title":"Thai text","summary":"Thai text","reasons":["Thai text"],"recommendations":["Thai text"]}
"""


def _factor_level(value: Optional[float], moderate: float, hot: float) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value >= hot:
        return "HOT"
    if value >= moderate:
        return "MODERATE"
    return "GOOD"


def _trend(values: list[Optional[float]], tolerance: float) -> str:
    if values[0] is None:
        return "insufficient_data"
    available = [value for value in reversed(values) if value is not None]
    if len(available) < 2:
        return "insufficient_data"
    change = available[-1] - available[0]
    if change > tolerance:
        return "rising"
    if change < -tolerance:
        return "falling"
    return "stable"


def summarize_readings(readings: list[SensorReading]) -> dict[str, Any]:
    """Calculate compact context in Python; never send raw rows to Groq."""

    latest = readings[0]
    co2_values = [reading.co2 for reading in readings if reading.co2 is not None]
    return {
        "sample_count": len(readings),
        "latest": {
            "temperature_c": latest.temperature,
            "humidity_percent": latest.humidity,
            "co2_ppm": latest.co2,
            "deterministic_status": latest.status,
        },
        "latest_factor_levels": {
            "co2": _factor_level(latest.co2, CO2_MODERATE_PPM, CO2_HOT_PPM),
            "temperature": _factor_level(
                latest.temperature, TEMPERATURE_MODERATE_C, TEMPERATURE_HOT_C
            ),
            "humidity": _factor_level(
                latest.humidity, HUMIDITY_MODERATE_PERCENT, HUMIDITY_HOT_PERCENT
            ),
        },
        "personalized_low_flags": {
            "temperature_low": latest.temperature <= LOW_TEMPERATURE_C,
            "humidity_low": latest.humidity <= LOW_HUMIDITY_PERCENT,
        },
        "recent_average": {
            "temperature_c": round(mean(reading.temperature for reading in readings), 1),
            "humidity_percent": round(mean(reading.humidity for reading in readings), 1),
            "co2_ppm": round(mean(co2_values), 1) if co2_values else None,
        },
        "trend": {
            "temperature": _trend([reading.temperature for reading in readings], 0.3),
            "humidity": _trend([reading.humidity for reading in readings], 2.0),
            "co2": _trend([reading.co2 for reading in readings], 100.0),
        },
    }


def _add(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def _co2_text(value: float) -> str:
    return f"{value:,.0f}"


def _decimal_text(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _selected_sensitivities_text(sensitivities: list[str]) -> str:
    descriptions = [SENSITIVITY_DESCRIPTIONS[item] for item in dict.fromkeys(sensitivities)]
    return " และ".join(descriptions)


def _profile_relevant_factors(summary: dict[str, Any], sensitivities: list[str]) -> list[str]:
    levels = summary["latest_factor_levels"]
    low = summary["personalized_low_flags"]
    factors: list[str] = []
    if ("poor_ventilation_sensitive" in sensitivities or "respiratory_sensitive" in sensitivities) and levels["co2"] in ("MODERATE", "HOT"):
        factors.append("co2_elevated")
    if ("high_humidity_sensitive" in sensitivities or "respiratory_sensitive" in sensitivities) and levels["humidity"] in ("MODERATE", "HOT"):
        factors.append("humidity_high")
    if "heat_sensitive" in sensitivities and levels["temperature"] in ("MODERATE", "HOT"):
        factors.append("temperature_high")
    if "cold_sensitive" in sensitivities and low["temperature_low"]:
        factors.append("temperature_low")
    if ("dry_air_sensitive" in sensitivities or "respiratory_sensitive" in sensitivities) and low["humidity_low"]:
        factors.append("humidity_low")
    return factors


def _measured_context(environment: AssessmentEnvironment) -> str:
    parts = [
        f"อุณหภูมิ {environment.temperature:g}°C",
        f"ความชื้น {environment.humidity:g}%",
    ]
    if environment.co2 is not None:
        parts.append(f"ค่า CO₂ ประมาณ {_co2_text(environment.co2)} ppm")
    return " ".join(parts[:-1]) + " และ" + parts[-1]


def _main_reason(reasons: list[str], environment: AssessmentEnvironment) -> str:
    """Lead with the most elevated measured factor in a short explanation."""

    def severity(reason: str) -> int:
        if "CO₂" in reason and environment.co2 is not None:
            return 2 if environment.co2 >= CO2_HOT_PPM else 1
        if "อุณหภูมิ" in reason:
            return 2 if environment.temperature >= TEMPERATURE_HOT_C else 1
        if "ความชื้น" in reason:
            return 2 if environment.humidity >= HUMIDITY_HOT_PERCENT else 1
        return 0

    return max(reasons, key=severity)


def _uncovered_elevated_factor(
    environment: AssessmentEnvironment, covered: set[str]
) -> Optional[tuple[str, str, str]]:
    """Explain an elevated measured factor behind status without citing the status code."""

    candidates = [
        ("co2", environment.co2, CO2_MODERATE_PPM, CO2_HOT_PPM),
        ("temperature", environment.temperature, TEMPERATURE_MODERATE_C, TEMPERATURE_HOT_C),
        ("humidity", environment.humidity, HUMIDITY_MODERATE_PERCENT, HUMIDITY_HOT_PERCENT),
    ]
    elevated = [
        (name, value, 2 if value >= hot else 1)
        for name, value, moderate, hot in candidates
        if value is not None and value >= moderate and name not in covered
    ]
    if not elevated:
        return None
    name, value, _level = max(elevated, key=lambda item: item[2])
    if name == "co2":
        return (
            "co2",
            f"ค่า CO₂ อยู่ที่ประมาณ {_co2_text(value)} ppm ซึ่งอาจสะท้อนว่าการระบายอากาศยังไม่เพียงพอ",
            "ลองเปิดหน้าต่างหรือประตูเพื่อเพิ่มอากาศจากภายนอก หากสภาพแวดล้อมภายนอกเหมาะสม",
        )
    if name == "temperature":
        return (
            "temperature",
            f"อุณหภูมิ {_decimal_text(value)}°C ค่อนข้างสูงในตอนนี้",
            "ลองเปิดพัดลมหรือปรับเครื่องปรับอากาศให้อยู่ในระดับที่รู้สึกสบาย",
        )
    return (
        "humidity",
        f"ความชื้น {_decimal_text(value)}% ค่อนข้างสูงในตอนนี้",
        "เพื่อลดความชื้น ลองใช้เครื่องปรับอากาศหรือเครื่องลดความชื้นหากมี",
    )


def fallback_assessment(
    environment: AssessmentEnvironment, sensitivities: list[str]
) -> Assessment:
    """Personalized Thai guidance when Groq is unavailable or untrusted."""

    reasons: list[str] = []
    recommendations: list[str] = []
    summary_issues: dict[str, tuple[int, str]] = {}
    relevant_sensitivities: list[str] = []
    covered: set[str] = set()
    severe = False
    temperature, humidity, co2 = (
        environment.temperature,
        environment.humidity,
        environment.co2,
    )

    if "heat_sensitive" in sensitivities and temperature >= TEMPERATURE_MODERATE_C:
        _add(reasons, f"อุณหภูมิ {_decimal_text(temperature)}°C ค่อนข้างสูงเมื่อคุณระบุว่าไวต่ออากาศร้อน")
        _add(recommendations, "ลองเปิดพัดลมหรือปรับเครื่องปรับอากาศให้อยู่ในระดับที่รู้สึกสบาย")
        summary_issues["temperature"] = (
            2 if temperature >= TEMPERATURE_HOT_C else 1,
            f"อุณหภูมิ {_decimal_text(temperature)}°C ค่อนข้างสูง",
        )
        _add(relevant_sensitivities, "heat_sensitive")
        covered.add("temperature")
        severe |= temperature >= TEMPERATURE_HOT_C

    if "cold_sensitive" in sensitivities and temperature <= LOW_TEMPERATURE_C:
        _add(reasons, f"อุณหภูมิ {_decimal_text(temperature)}°C ค่อนข้างต่ำเมื่อคุณระบุว่าไวต่ออากาศเย็น")
        _add(recommendations, "ลองปรับอุณหภูมิให้สบายขึ้นหรือเพิ่มเสื้อผ้าตามความเหมาะสม")
        summary_issues["temperature"] = (1, f"อุณหภูมิ {_decimal_text(temperature)}°C ค่อนข้างต่ำ")
        _add(relevant_sensitivities, "cold_sensitive")
        covered.add("temperature")

    if "high_humidity_sensitive" in sensitivities and humidity >= HUMIDITY_MODERATE_PERCENT:
        _add(reasons, f"ความชื้น {_decimal_text(humidity)}% ค่อนข้างสูงเมื่อคุณระบุว่าไวต่อความชื้นสูง")
        _add(recommendations, "เพื่อลดความชื้น ลองใช้เครื่องปรับอากาศหรือเครื่องลดความชื้นหากมี")
        _add(recommendations, "ติดตามค่าความชื้นหลังปรับสภาพแวดล้อม")
        summary_issues["humidity"] = (
            2 if humidity >= HUMIDITY_HOT_PERCENT else 1,
            f"ความชื้น {_decimal_text(humidity)}% ค่อนข้างสูง",
        )
        _add(relevant_sensitivities, "high_humidity_sensitive")
        if "respiratory_sensitive" in sensitivities:
            _add(relevant_sensitivities, "respiratory_sensitive")
        covered.add("humidity")
        severe |= humidity >= HUMIDITY_HOT_PERCENT

    if "dry_air_sensitive" in sensitivities and humidity <= LOW_HUMIDITY_PERCENT:
        _add(reasons, f"ความชื้น {_decimal_text(humidity)}% ค่อนข้างต่ำเมื่อคุณระบุว่าไวต่ออากาศแห้ง")
        _add(recommendations, "ลองปรับความชื้นให้สบายขึ้นและดูค่าที่วัดได้อีกครั้ง")
        summary_issues["humidity"] = (1, f"ความชื้น {_decimal_text(humidity)}% ค่อนข้างต่ำ")
        _add(relevant_sensitivities, "dry_air_sensitive")
        if "respiratory_sensitive" in sensitivities:
            _add(relevant_sensitivities, "respiratory_sensitive")
        covered.add("humidity")

    ventilation_selected = "poor_ventilation_sensitive" in sensitivities
    respiratory_selected = "respiratory_sensitive" in sensitivities
    if ventilation_selected or respiratory_selected:
        if co2 is None:
            ventilation_sensitivities = [
                item
                for item in ("poor_ventilation_sensitive", "respiratory_sensitive")
                if item in sensitivities
            ]
            _add(
                reasons,
                f"ตอนนี้ยังไม่มีค่า CO₂ จึงบอกเรื่องการระบายอากาศได้ไม่เต็มที่เมื่อคุณระบุว่า{_selected_sensitivities_text(ventilation_sensitivities)}",
            )
            _add(recommendations, "เมื่อมีค่า CO₂ แล้ว ลองดูประกอบกับความสบายของคุณ")
        elif co2 >= CO2_MODERATE_PPM:
            if ventilation_selected and respiratory_selected:
                sensitivity_text = "เมื่อคุณไวต่ออากาศอับและระบุว่าระบบทางเดินหายใจไวต่อสภาพแวดล้อม"
            elif ventilation_selected:
                sensitivity_text = "เมื่อคุณระบุว่าไวต่ออากาศอับ"
            else:
                sensitivity_text = "เมื่อคุณระบุว่าระบบทางเดินหายใจไวต่อสภาพแวดล้อม"
            _add(
                reasons,
                f"ค่า CO₂ อยู่ที่ประมาณ {_co2_text(co2)} ppm ซึ่งค่อนข้างสูงและอาจสะท้อนว่าการระบายอากาศยังไม่เพียงพอ {sensitivity_text}",
            )
            _add(recommendations, "ลองเปิดหน้าต่างหรือประตูเพื่อเพิ่มอากาศจากภายนอก หากสภาพแวดล้อมภายนอกเหมาะสม")
            _add(recommendations, "ติดตามค่า CO₂ อีกครั้งหลังเพิ่มการระบายอากาศ")
            summary_issues["co2"] = (
                2 if co2 >= CO2_HOT_PPM else 1,
                f"ค่า CO₂ ประมาณ {_co2_text(co2)} ppm ค่อนข้างสูง",
            )
            if ventilation_selected:
                _add(relevant_sensitivities, "poor_ventilation_sensitive")
            if respiratory_selected:
                _add(relevant_sensitivities, "respiratory_sensitive")
            covered.add("co2")
            severe |= co2 >= CO2_HOT_PPM

    if respiratory_selected and "humidity" not in covered and (humidity >= HUMIDITY_MODERATE_PERCENT or humidity <= LOW_HUMIDITY_PERCENT):
        _add(reasons, f"ความชื้น {_decimal_text(humidity)}% อาจทำให้คุณรู้สึกไม่สบายเมื่อระบบทางเดินหายใจไวต่อสภาพแวดล้อม")
        _add(recommendations, "ลองปรับความชื้นให้สบายขึ้นและดูค่าที่วัดได้อีกครั้ง")
        summary_issues["humidity"] = (
            2 if humidity >= HUMIDITY_HOT_PERCENT else 1,
            f"ความชื้น {_decimal_text(humidity)}% ค่อนข้าง{'สูง' if humidity >= HUMIDITY_MODERATE_PERCENT else 'ต่ำ'}",
        )
        _add(relevant_sensitivities, "respiratory_sensitive")
        covered.add("humidity")
        severe |= humidity >= HUMIDITY_HOT_PERCENT

    if environment.status == "HOT" or (environment.status == "MODERATE" and not reasons):
        extra = _uncovered_elevated_factor(environment, covered)
        if extra is not None:
            factor, reason, recommendation = extra
            _add(reasons, reason)
            _add(recommendations, recommendation)
            if factor == "co2":
                summary_issues[factor] = (2 if co2 >= CO2_HOT_PPM else 1, f"ค่า CO₂ ประมาณ {_co2_text(co2)} ppm ค่อนข้างสูง")
            elif factor == "temperature":
                summary_issues[factor] = (2 if temperature >= TEMPERATURE_HOT_C else 1, f"อุณหภูมิ {_decimal_text(temperature)}°C ค่อนข้างสูง")
            else:
                summary_issues[factor] = (2 if humidity >= HUMIDITY_HOT_PERCENT else 1, f"ความชื้น {_decimal_text(humidity)}% ค่อนข้างสูง")
        elif not reasons:
            _add(
                reasons,
                f"จากค่าที่วัดได้ตอนนี้ ({_measured_context(environment)}) ควรดูแนวโน้มต่อก่อนสรุปว่าเหมาะกับคุณ",
            )
            _add(recommendations, "สังเกตความสบายของคุณและดูค่าที่วัดได้อีกครั้ง")

    if severe:
        suitability, title = "NOT_SUITABLE", "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ"
    elif reasons:
        suitability, title = "CAUTION", "สภาพแวดล้อมตอนนี้ควรเฝ้าระวังเล็กน้อย"
    else:
        suitability, title = "SUITABLE", "สภาพแวดล้อมตอนนี้ค่อนข้างเหมาะกับคุณ"
        selected_measurements: list[str] = []
        if "heat_sensitive" in sensitivities or "cold_sensitive" in sensitivities:
            selected_measurements.append(f"อุณหภูมิ {_decimal_text(temperature)}°C")
        if "high_humidity_sensitive" in sensitivities or "dry_air_sensitive" in sensitivities or respiratory_selected:
            selected_measurements.append(f"ความชื้น {_decimal_text(humidity)}%")
        if (ventilation_selected or respiratory_selected) and co2 is not None:
            selected_measurements.append(f"ค่า CO₂ ประมาณ {_co2_text(co2)} ppm")
        reasons = [
            f"จากค่าที่วัดได้ตอนนี้ {' และ'.join(selected_measurements)} ยังดูเหมาะกับลักษณะที่คุณเลือก"
        ]
        recommendations = ["สังเกตความสบายของคุณและดูค่าที่วัดได้อีกครั้งเมื่อสภาพแวดล้อมเปลี่ยน"]

    if suitability == "SUITABLE":
        summary = reasons[0]
    elif summary_issues:
        factor_order = {"co2": 3, "humidity": 2, "temperature": 1}
        important = sorted(
            summary_issues.items(),
            key=lambda item: (item[1][0], factor_order[item[0]]),
            reverse=True,
        )[:2]
        phrases = [item[1][1] for item in important]
        if all(phrase.endswith(" ค่อนข้างสูง") for phrase in phrases):
            summary = f"{title} เพราะ{' และ'.join(phrase[:-len(' ค่อนข้างสูง')] for phrase in phrases)} ค่อนข้างสูง"
        else:
            summary = f"{title} เพราะ{' และ'.join(phrases)}"
        if relevant_sensitivities:
            selected_order = [item for item in sensitivities if item in relevant_sensitivities]
            summary += f" โดยเฉพาะเมื่อคุณระบุว่า{_selected_sensitivities_text(selected_order)}"
    else:
        summary = f"{title} เนื่องจาก{_main_reason(reasons, environment)}"
        if co2 is None and (ventilation_selected or respiratory_selected):
            summary += f" ขณะนี้อุณหภูมิ {temperature:g}°C และความชื้น {humidity:g}%"

    return Assessment(
        suitability=suitability,
        title=title,
        summary=summary,
        reasons=reasons[:4],
        recommendations=recommendations[:4],
    )


def _normalize_wording(assessment: Assessment) -> Assessment:
    """Repair harmless wording and spacing without changing measured claims."""

    def normalize(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r"\bapproximately\b", "ประมาณ", value, flags=re.IGNORECASE)
        value = value.replace("ทำให้ห้องรู้สึก", "ทำให้คุณรู้สึก")
        value = value.replace("ห้อง", "พื้นที่")
        return value

    return assessment.model_copy(update={
        "title": normalize(assessment.title),
        "summary": normalize(assessment.summary),
        "reasons": [normalize(item) for item in assessment.reasons],
        "recommendations": [normalize(item) for item in assessment.recommendations],
    })


def _text_validation_issue(assessment: Assessment) -> Optional[str]:
    values = [assessment.title, assessment.summary, *assessment.reasons, *assessment.recommendations]
    for value in values:
        if not re.search(r"[ก-๙]", value):
            return "non_thai_text"
        if re.search(
            r"ระบบตรวจพบ|ระบบประเมินว่า|ตามเกณฑ์ของระบบ|ตาม\s*threshold|จากการประมวลผลของระบบ|สถานะเซนเซอร์|ค่าเซนเซอร์",
            value,
            re.IGNORECASE,
        ):
            return "system_language"
        if re.search(
            r"(?<![A-Za-z])PM(?:\s*(?:2[.]?5|10))?(?![A-Za-z0-9])|particulate matter|VOC|ฝุ่น|อนุภาค|ละอองเกสร|ออกซิเจน|\bO2\b|(?<![A-Za-z])O₂|มลพิษ|AQI",
            value,
            re.IGNORECASE,
        ):
            return "unsupported_sensor_claim"
        if re.search(r"วินิจฉัย|เป็นโรค|โรค\S*|(?:รับประทาน|ใช้|กิน|ทาน)\s*ยา|ยาพ่น|ยาแก้|การรักษา|รักษาโรค|ปลอดภัยทางการแพทย์", value):
            return "medical_claim"
    return None


_MEASUREMENT_SUBJECTS = {
    "temperature": r"อุณหภูมิ|\d+(?:[.,]\d+)?\s*°\s*C",
    "humidity": r"ความชื้น|\d+(?:[.,]\d+)?\s*%",
    "co2": r"CO₂|CO2|คาร์บอนไดออกไซด์",
}
_OTHER_MEASUREMENT = re.compile(
    r"อุณหภูมิ|ความชื้น|CO₂|CO2|คาร์บอนไดออกไซด์|\.(?!\d)|(?<!\d)\.|[!?。ฯ\n]",
    re.IGNORECASE,
)
_HIGH_WORDS = {
    "temperature": r"สูง|ร้อน|อุ่น",
    "humidity": r"สูง|ชื้นเกินไป|ชื้นมาก|ชื้นจัด",
    "co2": r"สูง|มากเกินไป|เกินระดับ",
}
_LOW_WORDS = {
    "temperature": r"ต่ำ|เย็นเกินไป|เย็นมาก|หนาวเกินไป|หนาวมาก",
    "humidity": r"ต่ำ|แห้งเกินไป|แห้งมาก",
}


def _claims_condition(text: str, metric: str, qualifiers: str) -> bool:
    """Find an affirmative condition claim tied to one measured factor."""

    for subject in re.finditer(_MEASUREMENT_SUBJECTS[metric], text, re.IGNORECASE):
        prefix = text[max(0, subject.start() - 22):subject.start()]
        if re.search(r"(?:ไวต่อ|หาก|ถ้า|ในกรณีที่)\s*$", prefix):
            continue
        tail = text[subject.end():subject.end() + 75]
        boundary = _OTHER_MEASUREMENT.search(tail)
        fragment = tail[:boundary.start()] if boundary else tail
        for adjective in re.finditer(qualifiers, fragment):
            before = fragment[max(0, adjective.start() - 12):adjective.start()]
            if re.search(r"(?:ไม่|ไม่ได้|มิได้|ไม่ใช่|ไม่ถือว่า)\s*$", before):
                continue
            return True
    return False


def _valid_numeric_mentions(assessment: Assessment, context: dict[str, Any]) -> bool:
    """Allow normal rounding of current or recent-average measured values."""

    text = " ".join(
        [assessment.title, assessment.summary, *assessment.reasons, *assessment.recommendations]
    )
    latest = context["latest"]
    average = context["recent_average"]
    units = (
        (r"(\d[\d,]*(?:\.\d+)?)\s*ppm", "co2_ppm", 100.0),
        (r"(\d[\d,]*(?:\.\d+)?)\s*°\s*C", "temperature_c", 0.6),
        (r"(\d[\d,]*(?:\.\d+)?)\s*%", "humidity_percent", 1.0),
    )
    for pattern, key, tolerance in units:
        references = [value for value in (latest[key], average[key]) if value is not None]
        for match in re.finditer(pattern, text, re.IGNORECASE):
            mentioned = float(match.group(1).replace(",", ""))
            if not any(abs(mentioned - reference) <= tolerance for reference in references):
                return False
    # Also catch values written immediately after a sensor name without units.
    # Keep this narrow so unrelated numbers in everyday advice are unaffected.
    subject_values = (
        (r"(?:CO₂|CO2|คาร์บอนไดออกไซด์)", "co2_ppm", 100.0),
        (r"อุณหภูมิ", "temperature_c", 0.6),
        (r"ความชื้น", "humidity_percent", 1.0),
    )
    for subject, key, tolerance in subject_values:
        pattern = rf"{subject}\s*(?:(?:อยู่ที่|เท่ากับ|ประมาณ|ราว|:|=)\s*)?(\d[\d,]*(?:\.\d+)?)"
        references = [value for value in (latest[key], average[key]) if value is not None]
        for match in re.finditer(pattern, text, re.IGNORECASE):
            mentioned = float(match.group(1).replace(",", ""))
            if not any(abs(mentioned - reference) <= tolerance for reference in references):
                return False
    return True


def _measurement_validation_issue(
    assessment: Assessment, context: dict[str, Any]
) -> Optional[str]:
    levels = context["latest_factor_levels"]
    explanatory_text = " ".join(
        [assessment.title, assessment.summary, *assessment.reasons, *assessment.recommendations]
    )
    if levels["temperature"] == "GOOD":
        if _claims_condition(explanatory_text, "temperature", _HIGH_WORDS["temperature"]):
            return "normal_temperature_called_high"
        # A direct claim that the current environment is hot also implicates
        # temperature. Do not treat a generic mention of heat sensitivity as one.
        if re.search(
            r"(?:สภาพแวดล้อม|อากาศ)(?:ตอนนี้|ปัจจุบัน|ขณะนี้)?\s*ร้อน(?:เกินไป|จัด|มาก)",
            explanatory_text,
        ):
            return "normal_temperature_called_high"
    if levels["humidity"] == "GOOD" and _claims_condition(explanatory_text, "humidity", _HIGH_WORDS["humidity"]):
        return "normal_humidity_called_high"
    if levels["co2"] in ("GOOD", "UNAVAILABLE") and _claims_condition(explanatory_text, "co2", _HIGH_WORDS["co2"]):
        return "normal_co2_called_high"
    low = context["personalized_low_flags"]
    if not low["temperature_low"] and _claims_condition(explanatory_text, "temperature", _LOW_WORDS["temperature"]):
        return "normal_temperature_called_low"
    if not low["humidity_low"] and _claims_condition(explanatory_text, "humidity", _LOW_WORDS["humidity"]):
        return "normal_humidity_called_low"
    if not _valid_numeric_mentions(assessment, context):
        return "invented_measurement_value"
    return None


def _suitability_validation_issue(
    assessment: Assessment, context: dict[str, Any], expected: str
) -> Optional[str]:
    text = " ".join([assessment.title, assessment.summary, *assessment.reasons])
    if context["latest"]["deterministic_status"] == "HOT":
        if assessment.suitability == "SUITABLE" or re.search(
            r"(?:สภาพแวดล้อม(?:ตอนนี้|ปัจจุบัน)?\s*(?:ทุกอย่าง\s*)?ปกติ|สภาพแวดล้อม(?:ตอนนี้|ปัจจุบัน)?\s*(?:ค่อนข้าง\s*)?เหมาะ(?:สม)?|ทุกอย่างปกติ|ทุกค่า(?:อยู่ใน)?(?:ระดับ)?ปกติ|ไม่มีสิ่งที่ต้องกังวล|ไม่มีอะไรต้องกังวล|ไม่มีปัญหา)",
            text,
        ):
            return "status_contradiction"
    if assessment.suitability == expected:
        return None
    if expected == "NOT_SUITABLE" and assessment.suitability == "CAUTION":
        # The prose may already be appropriately cautious. The deterministic
        # enum and its title can be restored without changing a factual claim.
        return None
    return "suitability_contradiction"


def _fallback(reason: str) -> None:
    # Log reason codes only. Provider exceptions can contain request details.
    logger.info("AI assessment fallback: %s", reason)
    return None


def request_groq_assessment(
    summary: dict[str, Any], sensitivities: list[str], expected_suitability: str
) -> Optional[Assessment]:
    """Ask Groq for wording only; validate the result before using it."""

    api_key = get_groq_api_key()
    if api_key is None:
        return _fallback("missing_api_key")

    try:
        from groq import APIConnectionError, APIStatusError, APITimeoutError, Groq
    except ImportError:
        return _fallback("sdk_unavailable")

    try:
        with Groq(api_key=api_key, timeout=GROQ_TIMEOUT_SECONDS, max_retries=0) as client:
            completion = client.chat.completions.create(
                model=get_groq_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "sensitivities": sensitivities,
                                "sensor_context": summary,
                                "profile_relevant_factors": _profile_relevant_factors(
                                    summary, sensitivities
                                ),
                                "deterministic_suitability": expected_suitability,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        content = completion.choices[0].message.content
    except (APITimeoutError, TimeoutError):
        return _fallback("provider_timeout")
    except APIStatusError as exc:
        # HTTP status is safe to log; the provider response body is not.
        if exc.status_code == 429:
            return _fallback("provider_rate_limited")
        if exc.status_code in (401, 403):
            return _fallback("provider_auth_error")
        return _fallback("provider_http_error")
    except APIConnectionError:
        return _fallback("provider_connection_error")
    except Exception:
        return _fallback("provider_error")

    try:
        parsed = json.loads(content or "")
    except (ValueError, TypeError):
        return _fallback("invalid_json")
    try:
        assessment = _normalize_wording(Assessment.model_validate(parsed))
    except (ValidationError, TypeError):
        return _fallback("invalid_schema")

    try:
        issue = _text_validation_issue(assessment)
        if issue is None:
            issue = _measurement_validation_issue(assessment, summary)
        if issue is None:
            issue = _suitability_validation_issue(assessment, summary, expected_suitability)
    except Exception:
        return _fallback("validation_error")
    if issue is not None:
        return _fallback(issue)

    if assessment.suitability != expected_suitability:
        assessment = assessment.model_copy(update={
            "suitability": expected_suitability,
            "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
        })
    return assessment


def assess_environment(
    request: AssessmentRequest, readings: list[SensorReading]
) -> AssessmentResponse:
    latest = readings[0]
    environment = AssessmentEnvironment(
        temperature=latest.temperature,
        humidity=latest.humidity,
        co2=latest.co2,
        status=latest.status,
    )
    fallback = fallback_assessment(environment, request.sensitivities)
    groq_result = request_groq_assessment(
        summarize_readings(readings), request.sensitivities, fallback.suitability
    )
    return AssessmentResponse(
        success=True,
        source="groq" if groq_result is not None else "fallback",
        device_id=request.device_id,
        profile=request.sensitivities,
        environment=environment,
        assessment=groq_result or fallback,
        disclaimer=DISCLAIMER,
    )
