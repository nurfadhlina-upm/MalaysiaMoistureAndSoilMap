"""Unit tests for date selection and coordinate validation."""
import json
import unittest
from datetime import date
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

import pandas as pd
from app import (
    month_window,
    area_state_names,
    _static_area_bounds,
    validate_coordinates,
    validate_moisture_range,
    parse_optional_coordinates,
    parse_map_click,
    _map_tile_url,
    _render_map,
    _top_location_rows,
    _annual_frequency_rows,
    _soil_correlation_matrix,
    _csv_bytes,
    _map_visualization,
    _styled_correlation_matrix,
    _groq_map_context,
    _groq_chat_completion,
)


class _FakeCollection:
    def __init__(self):
        self.image = _FakeImage()

    def filterDate(self, start, end):
        return self

    def select(self, band):
        return self

    def size(self):
        return type("Size", (), {"getInfo": lambda self: 1})()

    def mean(self):
        return self.image


class _FakeImage:
    def clip(self, geometry):
        return self

    def rename(self, name):
        return self

    def getMapId(self, visualization):
        self.visualization = visualization
        return {"tile_fetcher": type("TileFetcher", (), {"url_format": "tiles"})()}


class _FakeEarthEngine:
    class Filter:
        @staticmethod
        def eq(*args):
            return None

    class _Boundaries:
        def filter(self, condition):
            return self

        def geometry(self):
            return object()

    def ImageCollection(self, dataset):
        self.collection = _FakeCollection()
        return self.collection

    def FeatureCollection(self, asset):
        return self._Boundaries()


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"The selected value is 0.31."}}]}'


class MalaysiaMoistureAndSoilMapTests(unittest.TestCase):
    def test_month_window_handles_leap_february(self):
        self.assertEqual(
            month_window(2024, 2),
            (date(2024, 2, 1), date(2024, 3, 1)),
        )

    def test_current_month_is_not_a_completed_period(self):
        today = date.today()
        with self.assertRaises(ValueError):
            month_window(today.year, today.month)

    def test_area_filters_cover_malaysia_regions_and_individual_admin_areas(self):
        self.assertIsNone(area_state_names("All Malaysia"))
        self.assertIn("W.P. Kuala Lumpur", area_state_names("Semenanjung Malaysia"))
        self.assertEqual(area_state_names("Sabah & Sarawak"), ("Sabah", "Sarawak", "W.P. Labuan"))
        self.assertEqual(area_state_names("Sabah"), ("Sabah",))
        self.assertNotEqual(_static_area_bounds("Semenanjung Malaysia"), _static_area_bounds("All Malaysia"))

    def test_coordinate_bounds(self):
        validate_coordinates(4.21, 101.97)
        with self.assertRaises(ValueError):
            validate_coordinates(91, 101.97)
        with self.assertRaises(ValueError):
            validate_coordinates(4.21, 181)
        with self.assertRaises(ValueError):
            validate_coordinates(float("nan"), 101.97)

    def test_map_click_parses_valid_coordinates_and_rejects_malformed_values(self):
        self.assertEqual(
            parse_map_click({"lat": 4.21, "lon": 101.97, "clickId": 1}),
            (4.21, 101.97),
        )
        self.assertIsNone(parse_map_click(None))
        with self.assertRaises(ValueError):
            parse_map_click({"lat": float("nan"), "lon": 101.97})

    def test_rendered_map_receives_the_selected_point_value(self):
        selected_point = {"lat": 4.21, "lon": 101.97}
        with patch("app._SOIL_MAP_COMPONENT", return_value=None) as component:
            _render_map(
                "map-tile-url",
                selected_point=selected_point,
                selected_value="0.321 m³/m³",
                selected_value_label="Monthly soil moisture",
            )

        self.assertEqual(component.call_args.kwargs["selected_point"], selected_point)
        self.assertEqual(
            component.call_args.kwargs["selected_value"],
            "0.321 m³/m³",
        )
        self.assertEqual(component.call_args.kwargs["key"], "soil_map_click")

    def test_map_moisture_range_requires_increasing_bounds(self):
        validate_moisture_range(0.0, 0.6)
        validate_moisture_range(0.2, 0.4)
        with self.assertRaises(ValueError):
            validate_moisture_range(0.4, 0.4)

    def test_map_slider_values_drive_the_raster_color_scale(self):
        today = date.today()
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        ee = _FakeEarthEngine()

        self.assertEqual(_map_tile_url(ee, year, month, 0.2, 0.4, "All Malaysia"), "tiles")
        self.assertEqual(ee.collection.image.visualization["min"], 0.2)
        self.assertEqual(ee.collection.image.visualization["max"], 0.4)

    def test_numeric_soil_map_uses_the_adjustable_display_range(self):
        visualization = _map_visualization(
            "ph", 0.0, 0.6, property_map_range=(4.5, 6.5)
        )

        self.assertEqual(visualization["min"], 4.5)
        self.assertEqual(visualization["max"], 6.5)
        self.assertTrue(visualization["palette"])

    def test_gps_coordinates_are_optional_but_must_be_a_valid_pair(self):
        self.assertEqual(parse_optional_coordinates("", ""), (None, None))
        self.assertEqual(
            parse_optional_coordinates("4.21", "101.97"),
            (4.21, 101.97),
        )
        with self.assertRaisesRegex(ValueError, "both latitude and longitude"):
            parse_optional_coordinates("4.21", "")
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            parse_optional_coordinates("north", "101.97")

    def test_top_locations_are_ranked_and_include_state_and_gps(self):
        features = [
            {
                "properties": {
                    "state_name": "Perak",
                    "district_name": "Kinta",
                    "monthly_moisture": 0.35,
                },
                "geometry": {"coordinates": [100.9, 4.8]},
            },
            {
                "properties": {
                    "state_name": "Kedah",
                    "district_name": "Kota Setar",
                    "monthly_moisture": 0.42,
                },
                "geometry": {"coordinates": [100.4, 6.1]},
            },
            {
                "properties": {
                    "state_name": "Pahang",
                    "district_name": "Kuantan",
                    "monthly_moisture": None,
                },
                "geometry": {"coordinates": [102.0, 4.0]},
            },
        ]
        rows, missing = _top_location_rows(features)

        self.assertEqual([row["State"] for row in rows], ["Perak", "Kedah"])
        self.assertEqual(rows[0]["Rank"], 1)
        self.assertEqual(rows[0]["Location name"], "Kinta")
        self.assertEqual((rows[0]["Latitude"], rows[0]["Longitude"]), (4.8, 100.9))
        self.assertEqual(missing, 1)

    def test_top_location_rows_include_soil_class_labels_and_properties(self):
        features = [
            {
                "properties": {
                    "state_name": "Sabah",
                    "district_name": "Kota Belud",
                    "monthly_moisture": 0.41,
                    "texture_class": 6,
                    "taxonomy_code": 402,
                    "ph": 5.1,
                    "clay": 39.9,
                },
                "geometry": {"coordinates": [116.5, 6.3]},
            }
        ]
        soil_classes = {
            "texture": [{"code": 6, "name": "Sandy clay loam"}],
            "taxonomy": [{"code": 402, "name": "Example great group"}],
        }

        rows, missing = _top_location_rows(features, soil_classes)

        self.assertEqual(missing, 0)
        self.assertEqual(rows[0]["USDA texture class (0 cm)"], "Sandy clay loam")
        self.assertEqual(rows[0]["USDA taxonomy great group"], "Example great group")
        self.assertEqual(rows[0]["Soil pH (0-5 cm)"], 5.1)
        self.assertEqual(rows[0]["Clay content (%)"], 39.9)

    def test_soil_correlation_matrix_uses_numeric_properties_and_monthly_moisture(self):
        samples = [
            {"monthly_moisture": 0.1, "ph": 4.0, "clay": 20, "texture_class": 6},
            {"monthly_moisture": 0.2, "ph": 5.0, "clay": 30, "texture_class": 7},
            {"monthly_moisture": 0.3, "ph": 6.0, "clay": 40, "texture_class": 8},
        ]

        matrix = _soil_correlation_matrix(samples)

        moisture = "Monthly mean moisture (m³/m³)"
        self.assertEqual(
            matrix.loc[moisture, "Soil pH (0-5 cm)"],
            1.0,
        )
        self.assertIn("Clay content (%)", matrix.columns)
        self.assertNotIn("texture_class", matrix.columns)

    def test_correlation_heatmap_keeps_values_and_applies_coloring(self):
        matrix = pd.DataFrame(
            [[1.0, -0.5], [-0.5, 1.0]],
            index=["Moisture", "Soil pH"],
            columns=["Moisture", "Soil pH"],
        )

        rendered = _styled_correlation_matrix(matrix).to_html()

        self.assertIn("1.00", rendered)
        self.assertIn("-0.50", rendered)
        self.assertIn("background-color:", rendered)

    def test_groq_context_omits_coordinates_but_includes_values(self):
        context = _groq_map_context(
            2025,
            12,
            "Sabah",
            "Soil pH (0-5 cm)",
            {"USDA texture": "All"},
            (4.0, 7.0),
            [{"State": "Sabah", "Latitude": 6.3, "Longitude": 116.5, "Soil pH": 5.2}],
            pd.DataFrame({"Soil pH": [0.4]}, index=["Monthly moisture"]),
            24,
            "5.2 pH",
        )

        serialized = json.dumps(context)
        self.assertIn("5.2 pH", serialized)
        self.assertIn("0.4", serialized)
        self.assertNotIn("Latitude", serialized)
        self.assertNotIn("116.5", serialized)

    def test_groq_chat_uses_configured_model_and_current_map_context(self):
        with patch("app.urlopen", return_value=_FakeResponse()) as mocked_urlopen:
            answer = _groq_chat_completion(
                "test-api-key",
                {"period": "December 2025", "map_value": 0.31},
                [{"role": "user", "content": "What does this value mean?"}],
                "llama-3.3-70b-versatile",
            )

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(answer, "The selected value is 0.31.")
        self.assertEqual(
            request.full_url,
            "https://api.groq.com/openai/v1/chat/completions",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer test-api-key")
        self.assertEqual(payload["model"], "llama-3.3-70b-versatile")
        self.assertIn("0.31", payload["messages"][0]["content"])

    def test_groq_http_errors_include_provider_reason_and_status_guidance(self):
        error = HTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            403,
            "Forbidden",
            None,
            BytesIO(
                b'{"error":{"type":"permission_error",'
                b'"message":"Account cannot access this model"}}'
            ),
        )
        with patch("app.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                _groq_chat_completion("test-api-key", {}, [], "test-model")

        self.assertIn(
            "permission_error: Account cannot access this model",
            str(raised.exception),
        )
        self.assertIn("access restriction", str(raised.exception))

    def test_groq_http_error_fallback_redacts_api_key(self):
        error = HTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            403,
            "Forbidden",
            None,
            BytesIO(b"Forbidden for test-api-key"),
        )
        with patch("app.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                _groq_chat_completion("test-api-key", {}, [], "test-model")

        self.assertIn("Forbidden for [redacted]", str(raised.exception))
        self.assertNotIn("test-api-key", str(raised.exception))

    def test_table_csv_is_utf8_and_does_not_add_an_unrequested_index(self):
        csv_text = _csv_bytes(
            [{"State": "Pulau Pinang", "Monthly mean moisture (m³/m³)": 0.42}]
        ).decode("utf-8-sig")

        self.assertTrue(csv_text.startswith("State,Monthly mean moisture"))
        self.assertIn("Pulau Pinang,0.42", csv_text)

    def test_annual_frequency_rank_uses_percent_of_valid_days(self):
        features = [
            {
                "properties": {
                    "state_name": "Sabah",
                    "location_name": "Kota Belud",
                    "monthly_rank": 1,
                    "wet_days": 60,
                    "valid_days": 300,
                },
                "geometry": {"coordinates": [116.4, 6.3]},
            },
            {
                "properties": {
                    "state_name": "Sarawak",
                    "location_name": "Kuching",
                    "monthly_rank": 2,
                    "wet_days": 180,
                    "valid_days": 300,
                },
                "geometry": {"coordinates": [110.3, 1.6]},
            },
        ]

        rows, missing, percent_column = _annual_frequency_rows(features, 0.35)

        self.assertEqual(missing, 0)
        self.assertEqual(percent_column, "Days ≥ 0.35 m³/m³ (%)")
        self.assertEqual([row["Nearest district"] for row in rows], ["Kuching", "Kota Belud"])
        self.assertEqual([row["Annual rank"] for row in rows], [1, 2])
        self.assertEqual([row[percent_column] for row in rows], [60.0, 20.0])


if __name__ == "__main__":
    unittest.main()
