"""Explore monthly soil moisture and daily readings at a GPS location."""
import calendar
import html
import json
import math
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


DATASET = "ECMWF/ERA5_LAND/DAILY_AGGR"
MOISTURE_BAND = "volumetric_soil_water_layer_1"
STATE_BOUNDARIES = "FAO/GAUL/2025/level1"
DISTRICT_BOUNDARIES = "FAO/GAUL/2025/level2"
SOIL_TEXTURE_ASSET = "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02"
SOIL_TAXONOMY_ASSET = "OpenLandMap/SOL/SOL_GRTGROUP_USDA-SOILTAX_C/v01"
FIRST_YEAR = 1950
APP_NAME = "MalaysiaMoistureAndSoilMap"
_SOIL_MAP_COMPONENT = components.declare_component(
    "malaysia_soil_map",
    path=str(Path(__file__).parent / "map_component"),
)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
PALETTE = ["#f6e8c3", "#dfc27d", "#80cdc1", "#35978f", "#01665e"]
TEXTURE_PALETTE = [
    "#d5c36b", "#b96947", "#9d3706", "#ae868f", "#f86714", "#46d143",
    "#368f20", "#3e5a14", "#ffd557", "#fff72e", "#ff5a9d", "#ff005b",
]
TEXTURE_NAMES = {
    1: "Clay",
    2: "Silty clay",
    3: "Sandy clay",
    4: "Clay loam",
    5: "Silty clay loam",
    6: "Sandy clay loam",
    7: "Loam",
    8: "Silt loam",
    9: "Sandy loam",
    10: "Silt",
    11: "Loamy sand",
    12: "Sand",
}
SOIL_PROPERTIES = {
    "ph": {
        "label": "Soil pH (0-5 cm)",
        "column": "Soil pH (0-5 cm)",
        "asset": "projects/soilgrids-isric/phh2o_mean",
        "band": "phh2o_0-5cm_mean",
        "scale": 0.1,
        "unit": "pH",
        "filter_range": (0.0, 14.0),
        "step": 0.1,
        "map_range": (3.0, 9.0),
    },
    "clay": {
        "label": "Clay content (%)",
        "column": "Clay content (%)",
        "asset": "projects/soilgrids-isric/clay_mean",
        "band": "clay_0-5cm_mean",
        "scale": 0.1,
        "unit": "%",
        "filter_range": (0.0, 100.0),
        "step": 1.0,
        "map_range": (0.0, 100.0),
    },
    "sand": {
        "label": "Sand content (%)",
        "column": "Sand content (%)",
        "asset": "projects/soilgrids-isric/sand_mean",
        "band": "sand_0-5cm_mean",
        "scale": 0.1,
        "unit": "%",
        "filter_range": (0.0, 100.0),
        "step": 1.0,
        "map_range": (0.0, 100.0),
    },
    "silt": {
        "label": "Silt content (%)",
        "column": "Silt content (%)",
        "asset": "projects/soilgrids-isric/silt_mean",
        "band": "silt_0-5cm_mean",
        "scale": 0.1,
        "unit": "%",
        "filter_range": (0.0, 100.0),
        "step": 1.0,
        "map_range": (0.0, 100.0),
    },
    "soc": {
        "label": "Organic carbon (g/kg)",
        "column": "Organic carbon (g/kg)",
        "asset": "projects/soilgrids-isric/soc_mean",
        "band": "soc_0-5cm_mean",
        "scale": 0.1,
        "unit": "g/kg",
        "filter_range": (0.0, 1000.0),
        "step": 5.0,
        "map_range": (0.0, 200.0),
    },
    "bdod": {
        "label": "Bulk density (g/cm³)",
        "column": "Bulk density (g/cm³)",
        "asset": "projects/soilgrids-isric/bdod_mean",
        "band": "bdod_0-5cm_mean",
        "scale": 0.01,
        "unit": "g/cm³",
        "filter_range": (0.0, 3.0),
        "step": 0.05,
        "map_range": (0.5, 2.0),
    },
    "cec": {
        "label": "Cation exchange capacity (cmol(c)/kg)",
        "column": "Cation exchange capacity (cmol(c)/kg)",
        "asset": "projects/soilgrids-isric/cec_mean",
        "band": "cec_0-5cm_mean",
        "scale": 0.1,
        "unit": "cmol(c)/kg",
        "filter_range": (0.0, 200.0),
        "step": 1.0,
        "map_range": (0.0, 50.0),
    },
    "nitrogen": {
        "label": "Total nitrogen (g/kg)",
        "column": "Total nitrogen (g/kg)",
        "asset": "projects/soilgrids-isric/nitrogen_mean",
        "band": "nitrogen_0-5cm_mean",
        "scale": 0.01,
        "unit": "g/kg",
        "filter_range": (0.0, 100.0),
        "step": 0.5,
        "map_range": (0.0, 50.0),
    },
}
STATE_NAMES = (
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang",
    "Perak", "Perlis", "Pulau Pinang", "Sabah", "Sarawak", "Selangor",
    "Terengganu", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya",
)
PENINSULAR_NAMES = (
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang",
    "Perak", "Perlis", "Pulau Pinang", "Selangor", "Terengganu",
    "W.P. Kuala Lumpur", "W.P. Putrajaya",
)
EAST_MALAYSIA_NAMES = ("Sabah", "Sarawak", "W.P. Labuan")
AREA_OPTIONS = (
    "All Malaysia",
    "Semenanjung Malaysia",
    "Sabah & Sarawak",
    *STATE_NAMES,
)
MALAYSIA_BOUNDS = [[0.7, 99.4], [7.6, 119.5]]
PENINSULAR_BOUNDS = [[1.1, 99.4], [7.5, 104.5]]
EAST_MALAYSIA_BOUNDS = [[0.7, 109.0], [7.6, 119.5]]


def month_window(year, month):
    """Return the inclusive start and exclusive end of a completed month."""
    today = date.today()
    if not FIRST_YEAR <= year <= today.year or not 1 <= month <= 12:
        raise ValueError("Choose a valid year and month.")
    if year == today.year and month >= today.month:
        raise ValueError("Choose a completed month.")
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def validate_coordinates(latitude, longitude):
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Latitude and longitude must be finite numbers.")
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees.")


def validate_moisture_range(minimum, maximum):
    if not 0 <= minimum < maximum <= 0.6:
        raise ValueError("Choose a moisture range above 0 and no higher than 0.60 m³/m³.")


def area_state_names(area):
    if area == "All Malaysia":
        return None
    if area == "Semenanjung Malaysia":
        return PENINSULAR_NAMES
    if area == "Sabah & Sarawak":
        return EAST_MALAYSIA_NAMES
    if area in STATE_NAMES:
        return (area,)
    raise ValueError("Choose a Malaysia region or state.")


def _initialize_earth_engine(project):
    import ee

    ee.Initialize(project=project)
    return ee


def _daily_collection(ee, year, month):
    start, end = month_window(year, month)
    return (
        ee.ImageCollection(DATASET)
        .filterDate(start.isoformat(), end.isoformat())
        .select(MOISTURE_BAND)
    )


def _filtered_states(ee, area):
    states = ee.FeatureCollection(STATE_BOUNDARIES).filter(
        ee.Filter.eq("GAUL0_NAME", "Malaysia")
    )
    names = area_state_names(area)
    if names is not None:
        states = states.filter(ee.Filter.inList("GAUL1_NAME", list(names)))
    return states


def _soil_image(ee, year, month):
    image = _daily_collection(ee, year, month).mean().rename("monthly_moisture")
    for key, config in SOIL_PROPERTIES.items():
        property_image = (
            ee.Image(config["asset"])
            .select(config["band"])
            .multiply(config["scale"])
            .rename(key)
        )
        image = image.addBands(property_image)
    texture = ee.Image(SOIL_TEXTURE_ASSET).select("b0").rename("texture_class")
    taxonomy = (
        ee.Image(SOIL_TAXONOMY_ASSET)
        .select("grtgroup")
        .rename("taxonomy_code")
    )
    return image.addBands(texture).addBands(taxonomy)


def _apply_soil_filters(
    ee,
    image,
    texture_codes=(),
    taxonomy_codes=(),
    property_ranges=(),
):
    if not texture_codes and not taxonomy_codes and not property_ranges:
        return image

    mask = image.select("texture_class").mask()
    if texture_codes:
        texture_mask = (
            image.select("texture_class")
            .remap(list(texture_codes), [1] * len(texture_codes), 0)
            .eq(1)
        )
        mask = mask.And(texture_mask)
    if taxonomy_codes:
        taxonomy_mask = (
            image.select("taxonomy_code")
            .remap(list(taxonomy_codes), [1] * len(taxonomy_codes), 0)
            .eq(1)
        )
        mask = mask.And(taxonomy_mask)
    for key, minimum, maximum in property_ranges:
        property_image = image.select(key)
        mask = mask.And(property_image.gte(minimum).And(property_image.lte(maximum)))
    return image.updateMask(mask)


def _class_codes(histogram, fallback_values):
    if not histogram:
        return sorted(int(value) for value in fallback_values if int(value) != 0)
    return sorted(
        {
            int(float(value))
            for value in histogram
            if int(float(value)) != 0
        }
    )


@st.cache_data(ttl=86400, max_entries=32, show_spinner=False)
def fetch_soil_classes(area, project):
    ee = _initialize_earth_engine(project)
    texture_image = ee.Image(SOIL_TEXTURE_ASSET).select("b0").rename("texture_class")
    taxonomy_image = (
        ee.Image(SOIL_TAXONOMY_ASSET)
        .select("grtgroup")
        .rename("taxonomy_code")
    )
    states = _filtered_states(ee, area)
    histograms = (
        texture_image.addBands(taxonomy_image)
        .reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=states.geometry(),
            scale=11132,
            maxPixels=1000000,
            tileScale=4,
        )
        .getInfo()
    )
    texture_properties = ee.Image(SOIL_TEXTURE_ASSET).getInfo()["properties"]
    taxonomy_properties = ee.Image(SOIL_TAXONOMY_ASSET).getInfo()["properties"]
    texture_metadata = dict(
        zip(
            texture_properties["b0_class_values"],
            texture_properties["b0_class_names"],
        )
    )
    taxonomy_metadata = dict(
        zip(
            taxonomy_properties["grtgroup_class_values"],
            taxonomy_properties["grtgroup_class_names"],
        )
    )
    taxonomy_values = [
        int(value) for value in taxonomy_properties["grtgroup_class_values"]
    ]
    taxonomy_palette = taxonomy_properties["grtgroup_class_palette"]
    taxonomy_colors = dict(zip(taxonomy_values, taxonomy_palette))
    texture_codes = _class_codes(
        histograms.get("texture_class"),
        texture_properties["b0_class_values"],
    )
    taxonomy_codes = _class_codes(
        histograms.get("taxonomy_code"),
        taxonomy_properties["grtgroup_class_values"],
    )
    return {
        "texture": [
            {
                "code": code,
                "name": TEXTURE_NAMES.get(
                    code, texture_metadata.get(code, f"Code {code}")
                ),
                "color": TEXTURE_PALETTE[code - 1]
                if 1 <= code <= len(TEXTURE_PALETTE)
                else "#64748b",
            }
            for code in texture_codes
        ],
        "taxonomy": [
            {
                "code": code,
                "name": taxonomy_metadata.get(
                    code, f"Unmapped USDA group (code {code})"
                ),
                "color": taxonomy_colors.get(code, "#64748b"),
            }
            for code in taxonomy_codes
        ],
        "taxonomy_palette": taxonomy_palette,
        "taxonomy_values": taxonomy_values,
    }


def _static_area_bounds(area):
    if area == "Semenanjung Malaysia":
        return PENINSULAR_BOUNDS
    if area == "Sabah & Sarawak":
        return EAST_MALAYSIA_BOUNDS
    return MALAYSIA_BOUNDS


def _map_visualization(
    map_layer,
    minimum,
    maximum,
    property_map_range=None,
    taxonomy_palette=None,
    taxonomy_values=(),
):
    if map_layer == "monthly_moisture":
        return {"min": minimum, "max": maximum, "palette": PALETTE}
    if map_layer == "texture_class":
        return {"min": 1, "max": 12, "palette": TEXTURE_PALETTE}
    if map_layer == "taxonomy_code":
        if taxonomy_values:
            return {
                "min": 0,
                "max": len(taxonomy_values),
                "palette": [*(taxonomy_palette or []), "#64748b"],
            }
        return {
            "min": 0,
            "max": 433,
            "palette": taxonomy_palette or PALETTE,
        }
    config = SOIL_PROPERTIES[map_layer]
    display_range = property_map_range or config["map_range"]
    return {
        "min": display_range[0],
        "max": display_range[1],
        "palette": PALETTE,
    }


def _map_tile_url(
    ee,
    year,
    month,
    minimum,
    maximum,
    area,
    map_layer="monthly_moisture",
    texture_codes=(),
    taxonomy_codes=(),
    property_ranges=(),
    property_map_range=None,
    taxonomy_palette=None,
    taxonomy_values=(),
):
    if map_layer == "monthly_moisture":
        validate_moisture_range(minimum, maximum)
    collection = _daily_collection(ee, year, month)
    if not collection.size().getInfo():
        return None
    area_geometry = _filtered_states(ee, area).geometry()
    if (
        map_layer == "monthly_moisture"
        and not texture_codes
        and not taxonomy_codes
        and not property_ranges
    ):
        image = collection.mean().rename("monthly_moisture")
    else:
        image = _soil_image(ee, year, month)
        image = _apply_soil_filters(
            ee, image, texture_codes, taxonomy_codes, property_ranges
        )
        if map_layer == "taxonomy_code" and taxonomy_values:
            taxonomy = image.select("taxonomy_code")
            image = taxonomy.remap(
                list(taxonomy_values),
                list(range(len(taxonomy_values))),
                len(taxonomy_values),
            ).updateMask(taxonomy.neq(0))
        else:
            image = image.select(map_layer)
    image = image.clip(area_geometry)
    visualization = _map_visualization(
        map_layer,
        minimum,
        maximum,
        property_map_range,
        taxonomy_palette,
        taxonomy_values,
    )
    map_info = image.getMapId(visualization)
    return map_info["tile_fetcher"].url_format


def parse_optional_coordinates(latitude_text, longitude_text):
    latitude_text = (latitude_text or "").strip()
    longitude_text = (longitude_text or "").strip()
    if not latitude_text and not longitude_text:
        return None, None
    if not latitude_text or not longitude_text:
        raise ValueError("Enter both latitude and longitude, or leave both blank.")
    try:
        latitude = float(latitude_text)
        longitude = float(longitude_text)
    except ValueError as exc:
        raise ValueError("Latitude and longitude must be numeric.") from exc
    validate_coordinates(latitude, longitude)
    return latitude, longitude


def parse_map_click(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("The map click did not contain valid coordinates.")
    try:
        latitude = float(value["lat"])
        longitude = float(value["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("The map click did not contain valid coordinates.") from exc
    validate_coordinates(latitude, longitude)
    return latitude, longitude


def _top_location_rows(features, soil_classes=None):
    rows = []
    missing_count = 0
    texture_names = {}
    taxonomy_names = {}
    if soil_classes:
        texture_names = {
            int(item["code"]): item["name"] for item in soil_classes["texture"]
        }
        taxonomy_names = {
            int(item["code"]): item["name"] for item in soil_classes["taxonomy"]
        }
    for feature in features:
        properties = feature.get("properties", {})
        state = properties.get("state_name")
        district = properties.get("district_name")
        moisture = properties.get("monthly_moisture")
        coordinates = feature.get("geometry", {}).get("coordinates")
        if (
            state is None
            or district is None
            or moisture is None
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            missing_count += 1
            continue
        longitude, latitude = coordinates[:2]
        row = {
            "Rank": len(rows) + 1,
            "State": state,
            "Location name": district,
            "Latitude": float(latitude),
            "Longitude": float(longitude),
            "Monthly mean moisture (m³/m³)": float(moisture),
        }
        if soil_classes:
            texture_code = properties.get("texture_class")
            taxonomy_code = properties.get("taxonomy_code")
            texture_code = int(float(texture_code)) if texture_code is not None else None
            taxonomy_code = int(float(taxonomy_code)) if taxonomy_code is not None else None
            row["USDA texture class (0 cm)"] = texture_names.get(
                texture_code, f"Unknown texture code {texture_code}"
            )
            row["Texture code"] = texture_code
            row["USDA taxonomy great group"] = taxonomy_names.get(
                taxonomy_code, f"Unknown taxonomy code {taxonomy_code}"
            )
            row["Taxonomy code"] = taxonomy_code
            for key, config in SOIL_PROPERTIES.items():
                value = properties.get(key)
                row[config["column"]] = float(value) if value is not None else None
        rows.append(row)
    return rows, missing_count


def _annual_frequency_rows(features, threshold):
    percent_column = f"Days ≥ {threshold:.2f} m³/m³ (%)"
    rows = []
    missing_count = 0
    for feature in features:
        properties = feature.get("properties", {})
        valid_days = properties.get("valid_days")
        wet_days = properties.get("wet_days")
        coordinates = feature.get("geometry", {}).get("coordinates")
        state = properties.get("state_name")
        district = properties.get("location_name")
        if (
            valid_days is None
            or wet_days is None
            or not valid_days
            or state is None
            or district is None
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            missing_count += 1
            continue
        longitude, latitude = coordinates[:2]
        rows.append(
            {
                "State": state,
                "Nearest district": district,
                "Latitude": float(latitude),
                "Longitude": float(longitude),
                "Wet days": int(wet_days),
                "Valid days": int(valid_days),
                percent_column: 100 * float(wet_days) / float(valid_days),
                "Monthly rank": int(properties.get("monthly_rank", 0)),
            }
        )
    rows.sort(key=lambda row: (-row[percent_column], row["Monthly rank"]))
    for rank, row in enumerate(rows, start=1):
        row["Annual rank"] = rank
    return rows, missing_count, percent_column


def _bounds_from_geometry(geometry):
    positions = [
        point
        for ring in geometry["coordinates"]
        for point in ring
    ]
    if not positions:
        raise ValueError("No map boundary is available for the selected area.")
    longitudes = [point[0] for point in positions]
    latitudes = [point[1] for point in positions]
    return [[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]]


@st.cache_data(ttl=86400, max_entries=48, show_spinner=False)
def fetch_area_bounds(area, project):
    if area in ("All Malaysia", "Semenanjung Malaysia", "Sabah & Sarawak"):
        return _static_area_bounds(area)
    ee = _initialize_earth_engine(project)
    geometry = _filtered_states(ee, area).geometry().bounds(11132).getInfo()
    return _bounds_from_geometry(geometry)


@st.cache_data(ttl=86400, max_entries=96, show_spinner=False)
def fetch_top_locations(
    year,
    month,
    project,
    area,
    texture_codes=(),
    taxonomy_codes=(),
    property_ranges=(),
    soil_classes=None,
):
    ee = _initialize_earth_engine(project)
    monthly_image = _soil_image(ee, year, month)
    monthly_image = _apply_soil_filters(
        ee, monthly_image, texture_codes, taxonomy_codes, property_ranges
    )
    states = _filtered_states(ee, area)
    districts = ee.FeatureCollection(DISTRICT_BOUNDARIES).filter(
        ee.Filter.eq("GAUL0_NAME", "Malaysia")
    )
    samples = (
        monthly_image.sample(
            region=states.geometry(),
            scale=11132,
            dropNulls=True,
            geometries=True,
            tileScale=4,
        )
        .sort("monthly_moisture", False)
        .limit(10)
    )

    def add_location_names(feature):
        point = feature.geometry()
        matching_states = states.filterBounds(point)
        matching_districts = districts.filterBounds(point)
        state_name = ee.Algorithms.If(
            matching_states.size().gt(0),
            matching_states.first().get("GAUL1_NAME"),
            "Unknown state",
        )
        district_name = ee.Algorithms.If(
            matching_districts.size().gt(0),
            matching_districts.first().get("GAUL2_NAME"),
            "District unavailable",
        )
        return feature.set(
            {"state_name": state_name, "district_name": district_name}
        )

    results = samples.map(add_location_names).getInfo()["features"]
    return _top_location_rows(results, soil_classes)


def _soil_correlation_matrix(samples):
    labels = {
        "monthly_moisture": "Monthly mean moisture (m³/m³)",
        **{
            key: config["column"]
            for key, config in SOIL_PROPERTIES.items()
        },
    }
    frame = pd.DataFrame(samples)
    if frame.empty:
        return pd.DataFrame(index=labels.values(), columns=labels.values())
    frame = frame.reindex(columns=labels.keys()).apply(
        pd.to_numeric, errors="coerce"
    )
    return frame.rename(columns=labels).corr(min_periods=2).round(3)


def _csv_bytes(data, include_index=False, index_label=None):
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    return frame.to_csv(
        index=include_index, index_label=index_label
    ).encode("utf-8-sig")


def _correlation_cell_style(value):
    if pd.isna(value):
        return ""
    neutral = (247, 247, 247)
    endpoint = (33, 102, 172) if value < 0 else (178, 24, 43)
    proportion = value + 1 if value < 0 else value
    color = tuple(
        round(start + (end - start) * proportion)
        for start, end in zip(endpoint if value < 0 else neutral,
                              neutral if value < 0 else endpoint)
    )
    return f"background-color: rgb{color}; color: #111827"


def _styled_correlation_matrix(matrix):
    def styles(data):
        return data.apply(lambda column: column.map(_correlation_cell_style))

    return matrix.style.apply(styles, axis=None).format("{:.2f}", na_rep="—")


def _gradient_legend_html(
    minimum,
    maximum,
    unit,
    palette=PALETTE,
    low_label=None,
    high_label=None,
):
    stops = ", ".join(palette)
    start = html.escape(
        f"{low_label}: {minimum:g} {unit}" if low_label else f"{minimum:g} {unit}"
    )
    end = html.escape(
        f"{high_label}: {maximum:g} {unit}" if high_label else f"{maximum:g} {unit}"
    )
    return (
        '<div class="flex items-center gap-2 text-xs text-slate-600">'
        f"<span>{start}</span>"
        f'<div class="h-2.5 w-28 rounded" style="background:linear-gradient(to right,{stops})"></div>'
        f"<span>{end}</span>"
        "</div>"
    )


def _groq_map_context(
    year,
    month,
    area,
    map_layer_label,
    active_filters,
    display_range,
    top_locations,
    correlation_matrix,
    sample_count,
    point_value,
):
    locations = [
        {
            key: value
            for key, value in row.items()
            if key not in ("Latitude", "Longitude")
        }
        for row in top_locations
    ]
    correlations = (
        correlation_matrix.to_dict(orient="index")
        if not correlation_matrix.empty
        else {}
    )
    return {
        "period": f"{calendar.month_name[month]} {year}",
        "area": area,
        "map_layer": map_layer_label,
        "map_display_range": display_range,
        "active_soil_filters": active_filters,
        "top_wettest_locations": locations,
        "correlation_sample_count": sample_count,
        "soil_moisture_correlations": correlations,
        "selected_point_map_value": point_value,
    }


def _categorical_legend_html(classes, include_codes=True):
    items = []
    for item in classes:
        code = f" {item['code']}" if include_codes else ""
        items.append(
            '<span class="whitespace-nowrap">'
            f'<i class="mr-1 inline-block h-2.5 w-2.5 rounded-sm" '
            f'style="background:{item["color"]}"></i>'
            f"{html.escape(item['name'])}{code}</span>"
        )
    return (
        '<div class="flex max-w-3xl flex-wrap gap-x-3 gap-y-1 text-[11px]">'
        + "".join(items)
        + "</div>"
    )


def _configured_groq_api_key():
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    try:
        return str(st.secrets.get("GROQ_API_KEY", "")).strip()
    except st.errors.StreamlitSecretNotFoundError:
        return ""


def _configured_groq_model():
    model = os.environ.get("GROQ_MODEL", "").strip()
    if model:
        return model
    try:
        model = str(st.secrets.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)).strip()
        return model or DEFAULT_GROQ_MODEL
    except st.errors.StreamlitSecretNotFoundError:
        return DEFAULT_GROQ_MODEL


def _safe_groq_error_text(value, api_key):
    detail = " ".join(value.split())
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    return detail[:500]


def _groq_http_error_detail(error, api_key):
    body = error.read().decode("utf-8", errors="replace")
    try:
        response_data = json.loads(body)
    except json.JSONDecodeError:
        return _safe_groq_error_text(body, api_key)
    if not isinstance(response_data, dict):
        return _safe_groq_error_text(body, api_key)
    response_error = response_data.get("error")
    if isinstance(response_error, str):
        return _safe_groq_error_text(response_error, api_key)
    if not isinstance(response_error, dict):
        return _safe_groq_error_text(body, api_key)
    details = [
        str(response_error[key]).strip()
        for key in ("type", "message")
        if isinstance(response_error.get(key), str)
        and response_error[key].strip()
    ]
    return _safe_groq_error_text(": ".join(details) or body, api_key)


def _groq_chat_completion(api_key, context, conversation, model):
    system_message = (
        f"You are the map assistant for {APP_NAME}. Use only the current map "
        "context below when describing selected values. These are modelled "
        "estimates, not field sensors. Explain units, distinguish correlation "
        "from causation, and say when the context does not contain enough "
        "information instead of inventing facts.\n\n"
        f"Current map context:\n{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    messages = [
        {"role": "system", "content": system_message},
        *conversation,
    ]
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_completion_tokens": 600,
        }
    ).encode("utf-8")
    request = Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        guidance = {
            401: "Check that GROQ_API_KEY is valid and active.",
            403: (
                "HTTP 403 usually means an access restriction. Check API-key, "
                "account, and model access; quota/rate-limit failures usually "
                "return HTTP 429. If no response detail is shown, check the "
                "Groq dashboard or contact Groq support."
            ),
            429: "Check your Groq rate limits and account quota, then retry.",
        }.get(exc.code, "Check the Groq request and account settings.")
        detail = _groq_http_error_detail(exc, api_key)
        message = f"Groq returned HTTP {exc.code}"
        if detail:
            message += f" ({detail})"
        raise RuntimeError(f"{message}. {guidance}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Groq: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("The Groq request timed out.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Groq returned an invalid response.") from exc
    try:
        answer = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Groq returned a response without an answer.") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Groq returned an empty answer.")
    return answer.strip()


def _render_groq_chat(context):
    st.markdown("### Ask Groq about this map")
    st.caption(
        "On submit, your question and a summary of the current map values are sent "
        "to Groq. GPS coordinates and source code are not included."
    )
    api_key = _configured_groq_api_key()
    if not api_key:
        st.info(
            "Configure `GROQ_API_KEY` in Streamlit secrets or the environment to enable Groq chat."
        )
    history = st.session_state.setdefault("groq_chat_history", [])
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input(
        "Ask about moisture, soil properties, or correlations...",
        disabled=not api_key,
        key="groq_chat_input",
    )
    if not prompt or not api_key:
        return
    user_message = {"role": "user", "content": prompt}
    history.append(user_message)
    with st.chat_message("user"):
        st.markdown(prompt)
    try:
        with st.spinner("Groq is reviewing the selected map values..."):
            answer = _groq_chat_completion(
                api_key, context, history[-8:], _configured_groq_model()
            )
    except RuntimeError as exc:
        with st.chat_message("assistant"):
            st.error(str(exc))
        return
    history.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)


@st.cache_data(ttl=86400, max_entries=96, show_spinner=False)
def fetch_soil_correlations(
    year,
    month,
    project,
    area,
    texture_codes=(),
    taxonomy_codes=(),
    property_ranges=(),
):
    ee = _initialize_earth_engine(project)
    image = _soil_image(ee, year, month)
    image = _apply_soil_filters(
        ee, image, texture_codes, taxonomy_codes, property_ranges
    )
    sample_bands = ["monthly_moisture", *SOIL_PROPERTIES.keys()]
    samples = image.select(sample_bands).sample(
        region=_filtered_states(ee, area).geometry(),
        scale=11132,
        dropNulls=True,
        geometries=False,
        tileScale=4,
    )
    features = samples.getInfo()["features"]
    rows = [feature.get("properties", {}) for feature in features]
    return _soil_correlation_matrix(rows), len(rows)


@st.cache_data(ttl=86400, max_entries=96, show_spinner=False)
def fetch_annual_frequency(locations, year, threshold, project):
    ee = _initialize_earth_engine(project)
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    collection = (
        ee.ImageCollection(DATASET)
        .filterDate(start.isoformat(), end.isoformat())
        .select(MOISTURE_BAND)
    )
    wet_days = collection.map(
        lambda image: image.gte(threshold).rename("wet_days")
    ).sum()
    valid_days = collection.count().rename("valid_days")
    daily_counts = wet_days.addBands(valid_days)
    points = ee.FeatureCollection(
        [
            ee.Feature(
                ee.Geometry.Point([location["Longitude"], location["Latitude"]]),
                {
                    "state_name": location["State"],
                    "location_name": location["Location name"],
                    "monthly_rank": location["Rank"],
                },
            )
            for location in locations
        ]
    )

    def count_at_location(feature):
        stats = daily_counts.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=feature.geometry(),
            scale=11132,
            maxPixels=10,
        )
        return feature.set(
            {
                "wet_days": stats.get("wet_days"),
                "valid_days": stats.get("valid_days"),
            }
        )

    features = points.map(count_at_location).getInfo()["features"]
    return _annual_frequency_rows(features, threshold)


@st.cache_data(ttl=86400, max_entries=64, show_spinner=False)
def fetch_daily_readings(year, month, latitude, longitude, project):
    ee = _initialize_earth_engine(project)
    collection = _daily_collection(ee, year, month)
    point = ee.Geometry.Point([longitude, latitude])

    def at_point(image):
        image_date = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd")
        moisture = image.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=11132,
            maxPixels=10,
        ).get(MOISTURE_BAND)
        return ee.Feature(None, {"date": image_date, "moisture": moisture})

    features = collection.map(at_point).getInfo()["features"]
    readings = [
        {
            "date": feature["properties"]["date"],
            "moisture": feature["properties"].get("moisture"),
        }
        for feature in features
    ]

    ph_image = (
        ee.Image("projects/soilgrids-isric/phh2o_mean")
        .select("phh2o_0-5cm_mean")
    )
    ph_values = ph_image.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=point,
        crs=ph_image.projection(),
        scale=250,
        maxPixels=10,
    ).getInfo()
    raw_ph = ph_values.get("phh2o_0-5cm_mean")
    mapped_ph = raw_ph / 10 if raw_ph is not None and 0 <= raw_ph <= 140 else None
    return readings, mapped_ph


@st.cache_data(ttl=86400, max_entries=96, show_spinner=False)
def fetch_map_point_value(
    year,
    month,
    latitude,
    longitude,
    project,
    map_layer,
    soil_classes,
    texture_codes=(),
    taxonomy_codes=(),
    property_ranges=(),
    area=None,
):
    ee = _initialize_earth_engine(project)
    image = _apply_soil_filters(
        ee,
        _soil_image(ee, year, month),
        texture_codes,
        taxonomy_codes,
        property_ranges,
    ).select(map_layer)
    if area is not None:
        image = image.clip(_filtered_states(ee, area).geometry())
    point = ee.Geometry.Point([longitude, latitude])
    scale = 11132 if map_layer == "monthly_moisture" else 250
    stats = image.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=point,
        scale=scale,
        maxPixels=100,
    ).getInfo()
    value = stats.get(map_layer)
    if value is None:
        return "Unavailable"
    if map_layer == "texture_class":
        code = int(float(value))
        names = {int(item["code"]): item["name"] for item in soil_classes["texture"]}
        return f"{names.get(code, f'Unknown texture code {code}')} (class {code})"
    if map_layer == "taxonomy_code":
        code = int(float(value))
        names = {int(item["code"]): item["name"] for item in soil_classes["taxonomy"]}
        return f"{names.get(code, f'Unknown taxonomy code {code}')} (code {code})"
    if map_layer == "monthly_moisture":
        return f"{float(value):.3f} m³/m³"
    config = SOIL_PROPERTIES[map_layer]
    return f"{float(value):.2f} {config['unit']}"


def _render_map(
    tile_url,
    latitude=None,
    longitude=None,
    moisture_min=0.0,
    moisture_max=0.6,
    map_bounds=None,
    layer_title="Monthly mean soil moisture",
    layer_description="ERA5-Land · layer 1 (0-7 cm) · m³/m³",
    legend_text=None,
    selected_point=None,
    selected_value=None,
    selected_value_label=None,
):
    if legend_text is None:
        legend_markup = _gradient_legend_html(
            moisture_min,
            moisture_max,
            "m³/m³",
            low_label="Drier",
            high_label="Wetter",
        )
    else:
        legend_markup = '<div class="text-xs text-slate-600">' + legend_text + "</div>"
    return _SOIL_MAP_COMPONENT(
        tile_url=tile_url,
        map_bounds=map_bounds or MALAYSIA_BOUNDS,
        latitude=latitude,
        longitude=longitude,
        layer_title=layer_title,
        layer_description=layer_description,
        legend_html=legend_markup,
        selected_point=selected_point,
        selected_value=selected_value,
        selected_value_label=selected_value_label or layer_title,
        default=None,
        key="soil_map_click",
    )


def _configured_project():
    project = os.environ.get("GEE_PROJECT")
    if project:
        return project
    try:
        return st.secrets.get("GEE_PROJECT", "")
    except st.errors.StreamlitSecretNotFoundError:
        return ""


def main():
    st.set_page_config(page_title=APP_NAME, page_icon="🌱", layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: #f5f8f6; }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { max-width: 1440px; padding-top: 2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(APP_NAME)
    st.caption(
        "Monthly soil-moisture maps across Malaysia. GPS coordinates are optional "
        "and zoom the map to a point for daily readings. Click the map to inspect "
        "the selected layer value. Choose a region or state to zoom and filter "
        "ranked locations."
    )

    today = date.today()
    latest_month = today.month - 1 or 12
    latest_year = today.year if today.month > 1 else today.year - 1
    year_key = "year"
    saved_year = st.session_state.get(year_key, latest_year)
    saved_year = min(max(saved_year, FIRST_YEAR), latest_year)
    if year_key in st.session_state and st.session_state[year_key] != saved_year:
        st.session_state[year_key] = saved_year

    controls = st.columns([1, 1, 1.8, 1])
    with controls[0]:
        year = st.slider(
            "Year", FIRST_YEAR, latest_year, saved_year, key=year_key
        )
    month_max = latest_month if year == latest_year else 12
    saved_month = st.session_state.get(
        "month", latest_month if year == latest_year else 12
    )
    saved_month = min(saved_month, month_max)
    if "month" in st.session_state and st.session_state["month"] != saved_month:
        st.session_state["month"] = saved_month
    with controls[1]:
        month = st.slider(
            "Month", 1, month_max, saved_month, key="month", format="%d"
        )
    with controls[2]:
        selected_area = st.selectbox(
            "Map area",
            AREA_OPTIONS,
            key="map_area",
            help="Zoom and limit the map and ranked locations to a region or state.",
        )
    with controls[3]:
        st.markdown("**Optional GPS location**")
        st.caption("Coordinates override map zoom; the area selection still filters results.")

    coordinates = st.columns(2)
    with coordinates[0]:
        latitude_text = st.text_input(
            "Latitude (optional)",
            placeholder="e.g. 4.2100",
            key="latitude_input",
        )
    with coordinates[1]:
        longitude_text = st.text_input(
            "Longitude (optional)",
            placeholder="e.g. 101.9700",
            key="longitude_input",
        )

    moisture_min, moisture_max = st.slider(
        "Map moisture range (m³/m³)",
        min_value=0.0,
        max_value=0.6,
        value=(0.0, 0.6),
        step=0.01,
        format="%.2f",
        key="moisture_map_range",
        help="Adjust the map colour scale; this does not filter the ranked locations or daily readings.",
    )
    annual_threshold = st.slider(
        "Annual wetness threshold (m³/m³)",
        min_value=0.0,
        max_value=0.6,
        value=0.35,
        step=0.01,
        format="%.2f",
        key="annual_wetness_threshold",
        help="Rank the 10 monthly locations by the percentage of valid days in the selected year at or above this moisture value.",
    )

    coordinate_error = None
    try:
        latitude, longitude = parse_optional_coordinates(latitude_text, longitude_text)
    except ValueError as exc:
        coordinate_error = str(exc)
        latitude, longitude = None, None
        st.warning(coordinate_error)

    month_window(year, month)
    st.subheader(f"{calendar.month_name[month]} {year}")

    project = _configured_project()
    if not project:
        _render_map(
            None,
            latitude,
            longitude,
            map_bounds=_static_area_bounds(selected_area),
        )
        st.info(
            "Set `GEE_PROJECT` in the environment or Streamlit secrets and authorize "
            "Earth Engine to load soil data."
        )
        return

    import ee

    try:
        ee = _initialize_earth_engine(project)
        with st.spinner("Loading soil texture and taxonomy classes..."):
            soil_classes = fetch_soil_classes(selected_area, project)
    except (ee.EEException, ValueError, OSError, KeyError) as exc:
        st.error(f"Could not load soil class metadata: {exc}")
        return

    st.markdown("#### Soil map controls")
    map_layer_options = {
        "Monthly soil moisture": "monthly_moisture",
        "USDA soil texture (0 cm)": "texture_class",
        "USDA soil taxonomy (great group)": "taxonomy_code",
    }
    map_layer_options.update(
        {config["label"]: key for key, config in SOIL_PROPERTIES.items()}
    )
    map_controls = st.columns(3)
    with map_controls[0]:
        map_layer_label = st.selectbox(
            "Map layer",
            list(map_layer_options),
            key="soil_map_layer",
        )
    texture_options = {
        f"{item['name']} (code {item['code']})": item["code"]
        for item in soil_classes["texture"]
    }
    taxonomy_options = {
        f"{item['name']} (code {item['code']})": item["code"]
        for item in soil_classes["taxonomy"]
    }
    with map_controls[1]:
        selected_texture_labels = st.multiselect(
            "USDA texture filter",
            list(texture_options),
            key=f"texture_filter_{selected_area}",
            help="Leave empty to include all texture classes.",
        )
    with map_controls[2]:
        selected_taxonomy_labels = st.multiselect(
            "USDA taxonomy filter",
            list(taxonomy_options),
            key=f"taxonomy_filter_{selected_area}",
            help="Great-group classes from the USDA Soil Taxonomy; leave empty to include all.",
        )
    texture_codes = tuple(
        texture_options[label] for label in selected_texture_labels
    )
    taxonomy_codes = tuple(
        taxonomy_options[label] for label in selected_taxonomy_labels
    )

    property_ranges = []
    with st.expander("Numeric soil-property filters (0-5 cm)", expanded=False):
        property_columns = st.columns(2)
        for index, (key, config) in enumerate(SOIL_PROPERTIES.items()):
            with property_columns[index % 2]:
                value_range = st.slider(
                    config["label"],
                    min_value=config["filter_range"][0],
                    max_value=config["filter_range"][1],
                    value=config["filter_range"],
                    step=config["step"],
                    format="%.2f" if config["step"] < 1 else "%.0f",
                    key=f"soil_range_{selected_area}_{key}",
                )
            if value_range != config["filter_range"]:
                property_ranges.append((key, value_range[0], value_range[1]))
    property_ranges = tuple(property_ranges)
    map_layer = map_layer_options[map_layer_label]
    property_map_range = None
    map_range_valid = True
    if map_layer in SOIL_PROPERTIES:
        config = SOIL_PROPERTIES[map_layer]
        property_map_range = st.slider(
            f"Map colour range ({config['unit']})",
            min_value=config["filter_range"][0],
            max_value=config["filter_range"][1],
            value=config["map_range"],
            step=config["step"],
            format="%.2f" if config["step"] < 1 else "%.0f",
            key=f"soil_map_display_range_{map_layer}",
            help="Adjust the raster colour scale. This does not filter locations.",
        )
        if property_map_range[0] >= property_map_range[1]:
            map_range_valid = False
            st.warning("Choose an increasing map colour range.")

    if map_layer == "monthly_moisture":
        try:
            validate_moisture_range(moisture_min, moisture_max)
        except ValueError as exc:
            map_range_valid = False
            st.warning(str(exc))

    try:
        map_click_point = parse_map_click(
            st.session_state.get("soil_map_click")
        )
    except ValueError as exc:
        map_click_point = None
        st.warning(f"Could not use the last map click: {exc}")

    if map_layer == "monthly_moisture":
        layer_title = f"Monthly mean soil moisture · {calendar.month_name[month]} {year}"
        layer_description = "ERA5-Land · layer 1 (0-7 cm) · m³/m³"
        legend_text = None
    elif map_layer == "texture_class":
        layer_title = "USDA soil texture class (0 cm)"
        layer_description = "OpenLandMap · static 250 m soil prediction"
        legend_text = _categorical_legend_html(
            [
                {"code": code, "name": name, "color": TEXTURE_PALETTE[code - 1]}
                for code, name in TEXTURE_NAMES.items()
            ]
        )
    elif map_layer == "taxonomy_code":
        layer_title = "USDA soil taxonomy great group"
        layer_description = "OpenLandMap · static 250 m soil prediction"
        legend_text = _categorical_legend_html(soil_classes["taxonomy"])
    else:
        config = SOIL_PROPERTIES[map_layer]
        layer_title = config["label"]
        layer_description = (
            f"Static SoilGrids estimate · 0-5 cm · {config['unit']}"
        )
        legend_text = _gradient_legend_html(
            property_map_range[0],
            property_map_range[1],
            config["unit"],
        )

    try:
        area_bounds = fetch_area_bounds(selected_area, project)
        tile_url = (
            _map_tile_url(
                ee,
                year,
                month,
                moisture_min,
                moisture_max,
                selected_area,
                map_layer=map_layer,
                texture_codes=texture_codes,
                taxonomy_codes=taxonomy_codes,
                property_ranges=property_ranges,
                property_map_range=property_map_range,
                taxonomy_palette=soil_classes["taxonomy_palette"],
                taxonomy_values=soil_classes["taxonomy_values"],
            )
            if map_range_valid
            else None
        )
    except (ee.EEException, ValueError, OSError) as exc:
        st.error(f"Could not load Earth Engine data: {exc}")
        return

    map_click_value = None
    if map_click_point is not None and tile_url is not None:
        try:
            with st.spinner("Reading the value at the clicked map location..."):
                map_click_value = fetch_map_point_value(
                    year,
                    month,
                    map_click_point[0],
                    map_click_point[1],
                    project,
                    map_layer,
                    soil_classes,
                    texture_codes,
                    taxonomy_codes,
                    property_ranges,
                    area=selected_area,
                )
        except (ee.EEException, ValueError, OSError, KeyError) as exc:
            st.error(f"Could not read the mapped value at the clicked location: {exc}")

    _render_map(
        tile_url,
        latitude,
        longitude,
        moisture_min,
        moisture_max,
        area_bounds,
        layer_title=layer_title,
        layer_description=layer_description,
        legend_text=legend_text,
        selected_point=(
            {"lat": map_click_point[0], "lon": map_click_point[1]}
            if map_click_point is not None
            else None
        ),
        selected_value=map_click_value,
        selected_value_label=map_layer_label,
    )
    if map_range_valid and tile_url is None:
        st.warning("No ERA5-Land observations are available for this month.")
        return

    if map_click_point is not None:
        st.metric(
            f"{map_layer_label} at clicked map location",
            map_click_value or "Unavailable",
        )

    point_value = map_click_value if map_click_point is not None else None
    if latitude is not None and longitude is not None:
        try:
            with st.spinner("Reading the selected map layer at the GPS point..."):
                point_value = fetch_map_point_value(
                    year,
                    month,
                    round(latitude, 4),
                    round(longitude, 4),
                    project,
                    map_layer,
                    soil_classes,
                    texture_codes,
                    taxonomy_codes,
                    property_ranges,
                )
            st.metric(f"{map_layer_label} at selected GPS point", point_value)
        except (ee.EEException, ValueError, OSError, KeyError) as exc:
            st.error(f"Could not read the mapped value at this GPS point: {exc}")

    st.markdown(f"### Top 10 wettest locations · {selected_area}")
    st.caption(
        "Ranked by monthly mean ERA5-Land soil moisture. Location names identify "
        "the nearest mapped district. USDA texture, taxonomy and numeric property "
        "filters apply to the map and ranked locations."
    )
    try:
        with st.spinner(f"Finding the 10 wettest grid cells in {selected_area}..."):
            top_locations, missing_locations = fetch_top_locations(
                year,
                month,
                project,
                selected_area,
                texture_codes,
                taxonomy_codes,
                property_ranges,
                soil_classes,
            )
    except (ee.EEException, ValueError, OSError) as exc:
        st.error(f"Could not calculate the top locations: {exc}")
        top_locations, missing_locations = [], 0
    if missing_locations:
        st.warning(
            f"{missing_locations} top grid location(s) could not be matched to a "
            "district or complete coordinates."
        )
    if top_locations:
        st.dataframe(
            pd.DataFrame(top_locations),
            hide_index=True,
            width="stretch",
            column_config={
                "Latitude": st.column_config.NumberColumn(format="%.4f"),
                "Longitude": st.column_config.NumberColumn(format="%.4f"),
                "Monthly mean moisture (m³/m³)": st.column_config.ProgressColumn(
                    "Monthly mean moisture (m³/m³)",
                    min_value=0.0,
                    max_value=0.6,
                    format="%.3f",
                ),
            },
        )
        st.caption(
            "SoilGrids numeric properties are static 0-5 cm estimates; USDA texture "
            "and taxonomy classes are static OpenLandMap estimates."
        )
        st.download_button(
            "Download top-10 soil table (CSV)",
            _csv_bytes(top_locations),
            file_name=f"malaysia_moisture_and_soil_map_top10_{year}_{month:02d}.csv",
            mime="text/csv",
            key="download_top_locations",
        )
    else:
        st.info("No top-location results are available for this month.")

    st.markdown(f"### Annual wetness frequency rank · {year}")
    st.caption(
        f"The same monthly top 10, ranked by the percentage of available daily "
        f"readings at or above {annual_threshold:.2f} m³/m³ in {year}."
    )
    if top_locations:
        try:
            with st.spinner("Calculating annual wetness frequency..."):
                frequency_rows, missing_frequency, percent_column = fetch_annual_frequency(
                    top_locations, year, annual_threshold, project
                )
        except (ee.EEException, ValueError, OSError) as exc:
            st.error(f"Could not calculate annual wetness frequency: {exc}")
            frequency_rows, missing_frequency, percent_column = [], 0, "Days ≥ threshold (%)"
        if missing_frequency:
            st.warning(
                f"Annual frequency was unavailable for {missing_frequency} location(s)."
            )
        if frequency_rows:
            st.dataframe(
                pd.DataFrame(frequency_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "Latitude": st.column_config.NumberColumn(format="%.4f"),
                    "Longitude": st.column_config.NumberColumn(format="%.4f"),
                    percent_column: st.column_config.ProgressColumn(
                        percent_column,
                        min_value=0.0,
                        max_value=100.0,
                        format="%.1f%%",
                    ),
                },
            )
            st.download_button(
                "Download annual frequency table (CSV)",
                _csv_bytes(frequency_rows),
                file_name=f"malaysia_moisture_and_soil_map_annual_frequency_{year}.csv",
                mime="text/csv",
                key="download_annual_frequency",
            )
        else:
            st.info("No annual frequency results are available for these locations.")

    st.markdown("### Soil-property correlation heatmap · monthly moisture")
    st.caption(
        "Pearson correlations use valid grid cells across the selected area and "
        "month after the soil filters above, not just the top 10. Categorical "
        "texture and taxonomy are excluded from Pearson correlation."
    )
    try:
        with st.spinner("Sampling soil and moisture across the selected area..."):
            correlation_matrix, sample_count = fetch_soil_correlations(
                year,
                month,
                project,
                selected_area,
                texture_codes,
                taxonomy_codes,
                property_ranges,
            )
    except (ee.EEException, ValueError, OSError) as exc:
        st.error(f"Could not calculate soil-property correlations: {exc}")
        correlation_matrix, sample_count = pd.DataFrame(), 0
    if sample_count < 2:
        st.info("Not enough valid grid cells to calculate a correlation matrix.")
    else:
        st.caption(
            f"Pearson correlation based on {sample_count:,} valid ERA5-Land grid cells."
        )
        st.caption("Blue indicates negative correlation; red indicates positive. Values are shown in each cell.")
        st.dataframe(_styled_correlation_matrix(correlation_matrix), width="stretch")
        st.download_button(
            "Download correlation matrix (CSV)",
            _csv_bytes(correlation_matrix, include_index=True, index_label="Variable"),
            file_name=f"malaysia_moisture_and_soil_map_correlations_{year}_{month:02d}.csv",
            mime="text/csv",
            key="download_soil_correlations",
        )

    active_filters = {
        "USDA texture": selected_texture_labels or "All",
        "USDA taxonomy": selected_taxonomy_labels or "All",
        "numeric soil-property ranges": property_ranges or "All",
    }
    display_range = (
        (moisture_min, moisture_max)
        if map_layer == "monthly_moisture"
        else property_map_range
    )
    chat_context = _groq_map_context(
        year,
        month,
        selected_area,
        map_layer_label,
        active_filters,
        display_range,
        top_locations,
        correlation_matrix,
        sample_count,
        point_value,
    )
    _render_groq_chat(chat_context)

    if latitude is None or longitude is None:
        if not coordinate_error:
            st.info("Enter both GPS coordinates to view daily moisture and pH at a point.")
        return

    try:
        with st.spinner("Loading daily readings for this location..."):
            readings, mapped_ph = fetch_daily_readings(
                year, month, round(latitude, 4), round(longitude, 4), project
            )
    except (ee.EEException, ValueError, OSError) as exc:
        st.error(f"Could not load daily readings for this location: {exc}")
        return

    daily = pd.DataFrame(readings)
    if daily.empty:
        st.warning("No daily readings are available at these coordinates for this month.")
        return
    daily["date"] = pd.to_datetime(daily["date"])
    daily["moisture"] = pd.to_numeric(daily["moisture"], errors="coerce")
    daily = daily.dropna(subset=["moisture"]).sort_values("date")
    if daily.empty:
        st.warning("This ERA5-Land grid cell has no valid daily readings.")
        return

    monthly_mean = daily["moisture"].mean()
    metrics = st.columns(3)
    metrics[0].metric("Monthly mean moisture", f"{monthly_mean:.3f} m³/m³")
    metrics[1].metric(
        "SoilGrids pH estimate",
        f"{mapped_ph:.1f}" if mapped_ph is not None else "Unavailable",
    )
    metrics[2].metric(
        "Daily readings",
        f"{len(daily)} / {calendar.monthrange(year, month)[1]}",
    )
    st.caption(
        "ERA5-Land values are modelled grid-cell estimates (~11 km), not in-field "
        "sensor readings. SoilGrids pH is a static 0-5 cm estimate, not a daily pH value."
    )

    charts = st.columns([1.5, 1])
    with charts[0]:
        st.markdown("#### Daily soil moisture")
        st.line_chart(daily.set_index("date")["moisture"], y_label="m³/m³")
    with charts[1]:
        st.markdown("#### Daily values")
        daily_view = daily.rename(
            columns={"date": "Date", "moisture": "Soil moisture (m³/m³)"}
        )
        daily_view["SoilGrids pH context (static)"] = mapped_ph
        st.dataframe(
            daily_view[["Date", "Soil moisture (m³/m³)", "SoilGrids pH context (static)"]],
            hide_index=True,
            width="stretch",
        )


if __name__ == "__main__":
    main()
