"""Tests for configured status resolution and environmental recommendations."""

import unittest

from pydantic import ValidationError

from backend.app.schemas import ReadingRequest
from backend.app.status import (
    determine_status,
    generate_recommendation,
    resolve_status,
)


class StatusResolutionTests(unittest.TestCase):
    def test_good_environment(self) -> None:
        self.assertEqual(determine_status(25, 55, 700), "GOOD")
        self.assertEqual(
            generate_recommendation(25, 55, 700),
            "Room conditions are within the configured comfort range. Continue monitoring.",
        )

    def test_moderate_due_to_co2(self) -> None:
        self.assertEqual(determine_status(25, 55, 1200), "MODERATE")
        self.assertIn("CO2 is elevated", generate_recommendation(25, 55, 1200))

    def test_hot_due_to_co2(self) -> None:
        self.assertEqual(determine_status(25, 55, 2000), "HOT")
        self.assertIn("CO2 is high", generate_recommendation(25, 55, 2000))

    def test_hot_due_to_temperature(self) -> None:
        self.assertEqual(determine_status(31, 55, 700), "HOT")
        self.assertIn("Room temperature is high", generate_recommendation(31, 55, 700))

    def test_hot_due_to_humidity(self) -> None:
        self.assertEqual(determine_status(25, 90, 700), "HOT")
        self.assertIn("Humidity is high", generate_recommendation(25, 90, 700))

    def test_multiple_hot_conditions_are_named(self) -> None:
        recommendation = generate_recommendation(31, 60, 2200)
        self.assertEqual(determine_status(31, 60, 2200), "HOT")
        self.assertIn("CO2 and room temperature are high", recommendation)
        self.assertIn("fresh-air ventilation", recommendation)
        self.assertIn("cooling or air circulation", recommendation)

    def test_device_status_is_authoritative(self) -> None:
        self.assertEqual(
            resolve_status(25, 50, "MODERATE", co2=700),
            "MODERATE",
        )

    def test_missing_or_null_status_uses_fallback(self) -> None:
        self.assertEqual(resolve_status(25, 75, None, co2=700), "MODERATE")
        self.assertEqual(resolve_status(25, 55, None, co2=2000), "HOT")

    def test_old_payload_without_status_is_valid(self) -> None:
        reading = ReadingRequest.model_validate(
            {
                "device_id": "smart-room-01",
                "temperature": 25,
                "humidity": 55,
                "co2": 700,
                "fan_on": False,
            }
        )
        self.assertIsNone(reading.status)

    def test_invalid_device_status_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReadingRequest.model_validate(
                {
                    "device_id": "smart-room-01",
                    "temperature": 25,
                    "humidity": 55,
                    "co2": 700,
                    "fan_on": False,
                    "status": "UNKNOWN",
                }
            )


if __name__ == "__main__":
    unittest.main()
