"""Assessment endpoint tests use SQLite and a mocked Groq SDK, never the network."""

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.ai_assessment import RECENT_WINDOW
from backend.app.database import get_db
from backend.app.main import app
from backend.app.models import Base, SensorReading


DEVICE = "smart-room-01"
PATH = "/api/v1/ai/assessment"


class AssessmentEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

        def test_db():
            with Session(self.engine, autoflush=False) as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def add_reading(
        self, device_id=DEVICE, temperature=29.2, humidity=65.0,
        co2=1850.0, status="HOT", fan_on=True,
    ) -> None:
        with Session(self.engine) as db:
            db.add(
                SensorReading(
                    device_id=device_id,
                    temperature=temperature,
                    humidity=humidity,
                    co2=co2,
                    status=status,
                    fan_on=fan_on,
                    recommendation="existing recommendation",
                )
            )
            db.commit()

    def assess(self, sensitivities, device_id=DEVICE):
        return self.client.post(
            PATH, json={"device_id": device_id, "sensitivities": sensitivities}
        )

    @staticmethod
    def mock_groq_answer(groq_class, **changes):
        answer = {
            "suitability": "NOT_SUITABLE",
            "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
            "summary": "ค่า CO₂ ประมาณ 2,093 ppm และความชื้น 87.3% ค่อนข้างสูง",
            "reasons": ["ค่า CO₂ ประมาณ 2,093 ppm ค่อนข้างสูงเมื่อคุณไวต่ออากาศอับ"],
            "recommendations": ["ลองเปิดหน้าต่างหรือประตูเพื่อเพิ่มการถ่ายเทอากาศ"],
        }
        answer.update(changes)
        groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps(
            answer, ensure_ascii=False
        )

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_one_sensitivity_uses_persisted_reading(self, _key) -> None:
        self.add_reading()
        self.add_reading(device_id="other-device", temperature=20, co2=500, status="GOOD")

        response = self.assess(["heat_sensitive"])

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["profile"], ["heat_sensitive"])
        self.assertEqual(body["environment"], {
            "temperature": 29.2, "humidity": 65.0, "co2": 1850.0, "status": "HOT"
        })
        self.assertEqual(body["assessment"]["suitability"], "CAUTION")
        self.assertIn("สภาพแวดล้อม", body["assessment"]["title"])
        explanation = json.dumps(body["assessment"], ensure_ascii=False)
        self.assertIn("29.2°C", explanation)
        self.assertIn("1,850 ppm", explanation)
        self.assertIn("ไวต่ออากาศร้อน", explanation)
        for phrase in ("ห้อง", "ตามเกณฑ์ของระบบ", "ระบบตรวจพบ", "ตาม threshold", "สถานะเซนเซอร์", "ฝุ่น", "PM"):
            self.assertNotIn(phrase, explanation)

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_multiple_sensitivities_and_missing_co2(self, _key) -> None:
        self.add_reading(co2=None, status="GOOD", temperature=25, humidity=55)
        response = self.assess(["poor_ventilation_sensitive", "respiratory_sensitive"])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["environment"]["co2"])
        self.assertEqual(body["assessment"]["suitability"], "CAUTION")
        self.assertTrue(any("ยังไม่มีค่า CO₂" in r for r in body["assessment"]["reasons"]))

    def test_empty_and_unsupported_sensitivities_rejected(self) -> None:
        self.assertEqual(self.assess([]).status_code, 422)
        self.assertEqual(self.assess(["dust_allergy"]).status_code, 422)
        self.assertEqual(self.assess(["heat_sensitive", "dust_allergy"]).status_code, 422)

    def test_missing_device_reading_returns_404(self) -> None:
        self.add_reading(device_id="other-device")
        self.assertEqual(self.assess(["heat_sensitive"]).status_code, 404)

    @patch("backend.app.ai_assessment.get_groq_model", return_value="openai/gpt-oss-20b")
    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_successful_mocked_groq_and_compact_context(self, groq_class, _key, _model) -> None:
        for index in range(RECENT_WINDOW + 3):
            self.add_reading(temperature=25 + index * 0.1, co2=1200 + index * 10, status="MODERATE")
        completion = MagicMock()
        completion.choices[0].message.content = json.dumps({
            "suitability": "CAUTION",
            "title": "สภาพแวดล้อมตอนนี้ควรเฝ้าระวัง",
            "summary": "ค่า CO₂ ประมาณ 1,340 ppm อาจทำให้คุณรู้สึกอับได้ง่ายเมื่อไวต่ออากาศอับ",
            "reasons": ["ค่า CO₂ ประมาณ 1,340 ppm อาจสะท้อนว่าการระบายอากาศยังไม่เพียงพอ"],
            "recommendations": ["ลองเพิ่มการถ่ายเทอากาศจากภายนอกหากทำได้"],
        }, ensure_ascii=False)
        groq_class.return_value.__enter__.return_value.chat.completions.create.return_value = completion

        response = self.assess(["poor_ventilation_sensitive", "respiratory_sensitive"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "groq")
        kwargs = groq_class.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
        context = json.loads(kwargs["messages"][1]["content"])
        self.assertEqual(context["sensor_context"]["sample_count"], RECENT_WINDOW)
        self.assertEqual(context["sensor_context"]["latest"]["co2_ppm"], 1340)
        self.assertEqual(context["sensor_context"]["recent_average"]["co2_ppm"], 1285.0)
        self.assertEqual(context["sensor_context"]["trend"]["co2"], "rising")
        self.assertEqual(context["sensor_context"]["latest_factor_levels"], {
            "co2": "MODERATE", "temperature": "GOOD", "humidity": "GOOD"
        })
        self.assertNotIn("configured_thresholds", context["sensor_context"])
        self.assertEqual(context["profile_relevant_factors"], ["co2_elevated"])
        self.assertNotIn("fan_on", kwargs["messages"][1]["content"])
        self.assertNotIn("recommendation", kwargs["messages"][1]["content"])
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertIn("poor_ventilation_sensitive=ไวต่ออากาศอับ", kwargs["messages"][0]["content"])
        self.assertEqual(groq_class.call_args.kwargs["max_retries"], 0)
        self.assertEqual(groq_class.call_args.kwargs["timeout"], 6.0)

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_timeout_uses_fallback(self, groq_class, _key) -> None:
        self.add_reading()
        groq_class.return_value.__enter__.return_value.chat.completions.create.side_effect = TimeoutError()
        with self.assertLogs("backend.app.ai_assessment", level="INFO") as logs:
            response = self.assess(["heat_sensitive", "poor_ventilation_sensitive"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fallback")
        self.assertEqual(response.json()["assessment"]["suitability"], "NOT_SUITABLE")
        self.assertEqual(logs.output, [
            "INFO:backend.app.ai_assessment:AI assessment fallback: provider_timeout"
        ])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_dust_or_system_language_uses_fallback(self, groq_class, _key) -> None:
        self.add_reading()
        for forbidden_summary in (
            "ค่า CO₂ เป็นฝุ่น",
            "ค่า CO₂ เป็น PM",
            "ค่า CO₂ เป็น PM2.5",
            "ค่า CO₂ เป็น PM10",
            "ค่า CO₂ เป็นอนุภาค",
            "ระบบตรวจพบค่า CO₂ สูง",
        ):
            with self.subTest(forbidden_summary=forbidden_summary):
                groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                    "suitability": "NOT_SUITABLE",
                    "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
                    "summary": forbidden_summary,
                    "reasons": ["ค่า CO₂ อยู่ที่ประมาณ 1,850 ppm"],
                    "recommendations": ["ลองเพิ่มการถ่ายเทอากาศ"],
                }, ensure_ascii=False)
                response = self.assess(["poor_ventilation_sensitive"])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["source"], "fallback")
                explanation = json.dumps(response.json()["assessment"], ensure_ascii=False)
                self.assertIn("1,850 ppm", explanation)
                self.assertNotIn(forbidden_summary, explanation)

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_suitable_fallback_uses_values_and_personal_context(self, _key) -> None:
        self.add_reading(temperature=25, humidity=55, co2=700, status="GOOD")
        response = self.assess(["heat_sensitive", "poor_ventilation_sensitive"])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["assessment"]["suitability"], "SUITABLE")
        self.assertIn("25°C", body["assessment"]["summary"])
        self.assertNotIn("55%", body["assessment"]["summary"])
        self.assertIn("700 ppm", body["assessment"]["summary"])
        self.assertIn("ลักษณะที่คุณเลือก", body["assessment"]["summary"])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_summary_prioritizes_high_co2_with_multiple_sensitivities(self, _key) -> None:
        self.add_reading(temperature=29.2, humidity=75, co2=1850, status="HOT")
        response = self.assess([
            "heat_sensitive", "high_humidity_sensitive", "poor_ventilation_sensitive"
        ])
        self.assertEqual(response.status_code, 200)
        summary = response.json()["assessment"]["summary"]
        self.assertIn("1,850 ppm", summary)
        self.assertIn("ไวต่ออากาศอับ", summary)

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_high_co2_and_humidity_do_not_turn_normal_temperature_into_problem(self, _key) -> None:
        self.add_reading(temperature=26.25, humidity=87.67, co2=2058, status="HOT")
        response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["assessment"]["suitability"], "NOT_SUITABLE")
        self.assertEqual(body["environment"]["temperature"], 26.25)
        self.assertIn("2,058 ppm", body["assessment"]["summary"])
        self.assertIn("87.7%", body["assessment"]["summary"])
        explanation = json.dumps(body["assessment"], ensure_ascii=False)
        self.assertNotIn("อุณหภูมิ", explanation)
        self.assertNotIn("ร้อนเกินไป", explanation)
        self.assertEqual(len(body["assessment"]["reasons"]), 2)
        self.assertIn("ลักษณะที่คุณเลือก", body["disclaimer"])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_high_co2_with_ventilation_sensitivity_focuses_on_ventilation(self, _key) -> None:
        self.add_reading(temperature=26.25, humidity=55, co2=2058, status="HOT")
        response = self.assess(["poor_ventilation_sensitive"])
        self.assertEqual(response.status_code, 200)
        body = response.json()["assessment"]
        self.assertIn("2,058 ppm", body["summary"])
        self.assertIn("ไวต่ออากาศอับ", body["summary"])
        self.assertEqual(len(body["reasons"]), 1)
        self.assertTrue(any("เปิดหน้าต่างหรือประตู" in item for item in body["recommendations"]))
        self.assertNotIn("อุณหภูมิ", json.dumps(body, ensure_ascii=False))

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_high_humidity_with_humidity_sensitivity_focuses_on_humidity(self, _key) -> None:
        self.add_reading(temperature=26.25, humidity=87.67, co2=700, status="HOT")
        response = self.assess(["high_humidity_sensitive"])
        self.assertEqual(response.status_code, 200)
        body = response.json()["assessment"]
        self.assertIn("87.7%", body["summary"])
        self.assertIn("ไวต่อความชื้นสูง", body["summary"])
        self.assertEqual(len(body["reasons"]), 1)
        self.assertTrue(any("เครื่องลดความชื้น" in item for item in body["recommendations"]))
        self.assertNotIn("CO₂", json.dumps(body, ensure_ascii=False))
        self.assertNotIn("อุณหภูมิ", json.dumps(body, ensure_ascii=False))

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_grounded_groq_answer_still_succeeds_for_mixed_readings(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.25, humidity=87.67, co2=2058, status="HOT")
        groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
            "suitability": "NOT_SUITABLE",
            "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
            "summary": "ค่า CO₂ ประมาณ 2,058 ppm และความชื้น 87.7% ค่อนข้างสูง โดยเฉพาะเมื่อคุณไวต่ออากาศอับและความชื้นสูง",
            "reasons": [
                "ค่า CO₂ อยู่ที่ประมาณ 2,058 ppm ซึ่งอาจสะท้อนว่าการถ่ายเทอากาศยังไม่เพียงพอ",
                "ความชื้นประมาณ 87.7% ค่อนข้างสูงเมื่อคุณไวต่อความชื้นสูง",
            ],
            "recommendations": [
                "ลองเปิดหน้าต่างหรือประตูเพื่อเพิ่มอากาศจากภายนอก หากภายนอกเหมาะสม",
                "ใช้เครื่องลดความชื้นหากมี",
            ],
        }, ensure_ascii=False)
        response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "groq")
        context = json.loads(
            groq_class.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        )
        self.assertEqual(context["sensor_context"]["latest_factor_levels"], {
            "co2": "HOT", "temperature": "GOOD", "humidity": "HOT"
        })
        self.assertEqual(context["profile_relevant_factors"], ["co2_elevated", "humidity_high"])
        self.assertEqual(set(response.json()), {
            "success", "source", "device_id", "profile", "environment", "assessment", "disclaimer"
        })

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_realistic_groq_answer_is_normalized_and_accepted(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.34, humidity=87.34, co2=2093, status="HOT")
        self.mock_groq_answer(
            groq_class,
            summary=(
                "อุณหภูมิ 26.3 °C อยู่ในระดับปกติ แต่คาร์บอนไดออกไซด์ 2,093 ppm "
                "และความชื้น 87.3 % สูงเกินไป ซึ่งอาจทำให้ห้องรู้สึกอับและไม่สบาย"
            ),
            reasons=[
                "ค่า CO₂ 2,093 ppm ค่อนข้างสูง โดยเฉพาะเมื่อคุณไวต่ออากาศอับ",
                "ความชื้น 87.3% ค่อนข้างสูงเมื่อคุณไวต่อความชื้นสูง",
            ],
        )
        response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "groq")
        self.assertIn("ทำให้คุณรู้สึกอับ", response.json()["assessment"]["summary"])
        self.assertNotIn("ห้อง", json.dumps(response.json()["assessment"], ensure_ascii=False))

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_high_humidity_then_normal_temperature_is_accepted(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.34, humidity=87.34, co2=2093, status="HOT")
        self.mock_groq_answer(
            groq_class,
            summary="ความชื้นสูง แต่อุณหภูมิประมาณ 26.3°C ขณะที่ค่า CO₂ 2,093 ppm ค่อนข้างสูงสำหรับผู้ที่ไวต่ออากาศอับ",
        )
        response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
        self.assertEqual(response.json()["source"], "groq")
        self.assertIn("อุณหภูมิประมาณ 26.3°C", response.json()["assessment"]["summary"])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_equivalent_co2_formats_are_accepted(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.34, humidity=87.34, co2=2093, status="HOT")
        for value in ("2093", "2,093", "2093.0", "approximately 2,093", "ประมาณ 2,093"):
            with self.subTest(value=value):
                self.mock_groq_answer(
                    groq_class,
                    summary=f"ค่า CO₂ {value} ppm และความชื้น 87% ค่อนข้างสูงเมื่อคุณไวต่ออากาศอับและความชื้นสูง",
                )
                response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
                self.assertEqual(response.json()["source"], "groq")
                self.assertNotIn("approximately", response.json()["assessment"]["summary"])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_specific_invalid_claims_log_reason_only(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.34, humidity=87.34, co2=2093, status="HOT")
        examples = (
            ("อุณหภูมิ 26.3°C สูงเกินไป", "normal_temperature_called_high"),
            ("ค่าฝุ่น 2,093 ppm สูง", "unsupported_sensor_claim"),
            ("PM2.5 อยู่ที่ 2,093", "unsupported_sensor_claim"),
            ("ค่า CO₂ ประมาณ 3,000 ppm สูง", "invented_measurement_value"),
            ("ค่า CO₂ 3,000 ค่อนข้างสูง", "invented_measurement_value"),
        )
        for summary, expected_reason in examples:
            with self.subTest(summary=summary):
                self.mock_groq_answer(groq_class, summary=summary)
                with self.assertLogs("backend.app.ai_assessment", level="INFO") as logs:
                    response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
                self.assertEqual(response.json()["source"], "fallback")
                self.assertEqual(logs.output, [
                    f"INFO:backend.app.ai_assessment:AI assessment fallback: {expected_reason}"
                ])
                self.assertNotIn("test-placeholder", logs.output[0])
                self.assertNotIn("poor_ventilation_sensitive", logs.output[0])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_cautious_suitability_enum_is_normalized_without_rejecting_prose(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.34, humidity=87.34, co2=2093, status="HOT")
        self.mock_groq_answer(
            groq_class,
            suitability="CAUTION",
            title="สภาพแวดล้อมตอนนี้ควรเฝ้าระวังเล็กน้อย",
            summary="สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ เพราะค่า CO₂ 2,093 ppm และความชื้น 87.3% ค่อนข้างสูง",
        )
        response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
        self.assertEqual(response.json()["source"], "groq")
        self.assertEqual(response.json()["assessment"]["suitability"], "NOT_SUITABLE")
        self.assertEqual(response.json()["assessment"]["title"], "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ")

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_hot_environment_called_entirely_normal_is_rejected(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.34, humidity=87.34, co2=2093, status="HOT")
        self.mock_groq_answer(
            groq_class,
            suitability="CAUTION",
            summary="สภาพแวดล้อมทุกอย่างปกติดี ไม่มีสิ่งที่ต้องกังวล",
        )
        with self.assertLogs("backend.app.ai_assessment", level="INFO") as logs:
            response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
        self.assertEqual(response.json()["source"], "fallback")
        self.assertEqual(logs.output, [
            "INFO:backend.app.ai_assessment:AI assessment fallback: status_contradiction"
        ])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_normal_temperature_overheating_claim_uses_fallback(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.25, humidity=87.67, co2=2058, status="HOT")
        for bad_summary in (
            "อุณหภูมิ 26°C สูง ร่วมกับความชื้น 87.7%",
            "อุณหภูมิ 26.25°C ค่อนข้างสูง",
            "อุณหภูมิ 26°C อยู่ในช่วงอุ่นแต่ร่วมกับความชื้นทำให้ร้อนเกินไป",
            "สภาพแวดล้อมตอนนี้ร้อนเกินไป แม้ค่า CO₂ อยู่ที่ 2,058 ppm",
        ):
            with self.subTest(bad_summary=bad_summary):
                groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                    "suitability": "NOT_SUITABLE",
                    "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
                    "summary": bad_summary,
                    "reasons": ["ค่า CO₂ ประมาณ 2,058 ppm ค่อนข้างสูง"],
                    "recommendations": ["ลองเพิ่มการถ่ายเทอากาศ", "ดูค่า CO₂ อีกครั้ง"],
                }, ensure_ascii=False)
                response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["source"], "fallback")
                self.assertNotIn("ร้อนเกินไป", response.json()["assessment"]["summary"])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_invented_sensor_quantity_or_oxygen_uses_fallback(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.25, humidity=87.67, co2=2058, status="HOT")
        for bad_summary in (
            "ค่า CO₂ ประมาณ 3,000 ppm ค่อนข้างสูง",
            "ค่าออกซิเจนต่ำเพราะ CO₂ สูง",
        ):
            with self.subTest(bad_summary=bad_summary):
                groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                    "suitability": "NOT_SUITABLE",
                    "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
                    "summary": bad_summary,
                    "reasons": ["ความชื้น 87.7% ค่อนข้างสูง"],
                    "recommendations": ["ลองเพิ่มการถ่ายเทอากาศ", "ดูค่าความชื้นอีกครั้ง"],
                }, ensure_ascii=False)
                response = self.assess(["poor_ventilation_sensitive", "high_humidity_sensitive"])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["source"], "fallback")

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_normal_humidity_and_temperature_claims_use_fallback(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.25, humidity=55, co2=2058, status="HOT")
        for bad_summary in (
            "ความชื้น 55% สูงเกินไป",
            "ความชื้น 55% แห้งเกินไป",
            "อุณหภูมิ 26.25°C ต่ำเกินไป",
        ):
            with self.subTest(bad_summary=bad_summary):
                groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
                    "suitability": "NOT_SUITABLE",
                    "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
                    "summary": bad_summary,
                    "reasons": ["ค่า CO₂ ประมาณ 2,058 ppm ค่อนข้างสูง"],
                    "recommendations": ["ลองเพิ่มการถ่ายเทอากาศ", "ดูค่า CO₂ อีกครั้ง"],
                }, ensure_ascii=False)
                response = self.assess(["poor_ventilation_sensitive", "dry_air_sensitive", "cold_sensitive"])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["source"], "fallback")

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_normal_co2_cannot_be_called_high(self, groq_class, _key) -> None:
        self.add_reading(temperature=26.25, humidity=87.67, co2=700, status="HOT")
        groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
            "suitability": "NOT_SUITABLE",
            "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
            "summary": "ค่า CO₂ 700 ppm สูง และความชื้น 87.7% สูง",
            "reasons": ["ความชื้น 87.7% ค่อนข้างสูง"],
            "recommendations": ["ใช้เครื่องลดความชื้นหากมี", "ติดตามค่าความชื้นอีกครั้ง"],
        }, ensure_ascii=False)
        response = self.assess(["high_humidity_sensitive"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fallback")

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_invalid_json_uses_fallback(self, groq_class, _key) -> None:
        self.add_reading()
        groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = "invalid"
        with self.assertLogs("backend.app.ai_assessment", level="INFO") as logs:
            response = self.assess(["heat_sensitive"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fallback")
        self.assertEqual(logs.output, [
            "INFO:backend.app.ai_assessment:AI assessment fallback: invalid_json"
        ])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_provider_error_and_invalid_schema_log_distinct_reasons(self, groq_class, _key) -> None:
        self.add_reading()
        create = groq_class.return_value.__enter__.return_value.chat.completions.create
        create.side_effect = RuntimeError("secret-bearing provider detail")
        with self.assertLogs("backend.app.ai_assessment", level="INFO") as logs:
            response = self.assess(["heat_sensitive"])
        self.assertEqual(response.json()["source"], "fallback")
        self.assertEqual(logs.output, [
            "INFO:backend.app.ai_assessment:AI assessment fallback: provider_error"
        ])

        create.side_effect = None
        create.return_value.choices[0].message.content = json.dumps({"suitability": "NOT_SUITABLE"})
        with self.assertLogs("backend.app.ai_assessment", level="INFO") as logs:
            response = self.assess(["heat_sensitive"])
        self.assertEqual(response.json()["source"], "fallback")
        self.assertEqual(logs.output, [
            "INFO:backend.app.ai_assessment:AI assessment fallback: invalid_schema"
        ])

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value="test-placeholder")
    @patch("groq.Groq")
    def test_groq_cannot_override_authoritative_hot_guardrail(self, groq_class, _key) -> None:
        self.add_reading(temperature=31)
        groq_class.return_value.__enter__.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
            "suitability": "SUITABLE",
            "title": "สภาพแวดล้อมเหมาะสม",
            "summary": "สภาพแวดล้อมปกติ",
            "reasons": ["ค่าปกติ"],
            "recommendations": ["ติดตามค่าต่อเนื่อง"],
        }, ensure_ascii=False)
        response = self.assess(["heat_sensitive"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fallback")
        self.assertEqual(response.json()["environment"]["status"], "HOT")
        self.assertEqual(response.json()["assessment"]["suitability"], "NOT_SUITABLE")

    @patch("backend.app.ai_assessment.get_groq_api_key", return_value=None)
    def test_missing_key_and_existing_telemetry_are_unaffected(self, _key) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        created = self.client.post("/api/v1/readings", json={
            "device_id": DEVICE, "temperature": 31.0, "humidity": 55.0,
            "co2": 700.0, "fan_on": True, "status": "MODERATE",
        })
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "MODERATE")
        self.assertIn("Room temperature is high", created.json()["recommendation"])
        before_latest = self.client.get("/api/v1/readings/latest").json()
        before_history = self.client.get("/api/v1/readings?limit=10").json()

        assessed = self.assess(["heat_sensitive"])

        self.assertEqual(assessed.status_code, 200)
        self.assertEqual(assessed.json()["source"], "fallback")
        self.assertEqual(assessed.json()["environment"]["status"], "MODERATE")
        self.assertEqual(self.client.get("/api/v1/readings/latest").json(), before_latest)
        self.assertEqual(self.client.get("/api/v1/readings?limit=10").json(), before_history)
        with Session(self.engine) as db:
            self.assertEqual(db.query(SensorReading).count(), 1)
            self.assertTrue(db.query(SensorReading).first().fan_on)


if __name__ == "__main__":
    unittest.main()
