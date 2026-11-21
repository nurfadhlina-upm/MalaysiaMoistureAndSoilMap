# MalaysiaMoistureAndSoilMap

A standalone Streamlit web app for monthly soil-moisture maps and daily point readings.

## Run locally

Python 3.10 or later is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.example.toml .streamlit\secrets.toml
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Set `GEE_PROJECT` in `.streamlit\secrets.toml` or the environment. Authenticate the
Earth Engine account used by the app with:

```powershell
.\.venv\Scripts\python.exe -c "import ee; ee.Authenticate()"
```

Make sure that account can access the selected Google Cloud project.

To enable the Groq chat box, set `GROQ_API_KEY` in `.streamlit\secrets.toml` or
the environment. `GROQ_MODEL` is optional and defaults to
`llama-3.3-70b-versatile`. The key is read server-side and is never placed in
the page or sent to the browser. An environment variable overrides the matching
value in Streamlit secrets, so clear any stale `GROQ_API_KEY` or `GROQ_MODEL`
environment settings if you intend to use the secrets-file values. Chat errors
include Groq's reported reason;
HTTP 403 usually indicates an access restriction, while HTTP 429 indicates a
rate-limit or quota issue.

The map uses the daily ERA5-Land layer-1 volumetric soil-water band (0-7 cm).
Daily values are modelled grid-cell estimates at approximately 11 km resolution,
not sensor measurements. The displayed pH comes from the static SoilGrids
0-5 cm estimate; pH is not measured daily by these sources. The map uses Leaflet,
OpenStreetMap tiles and Tailwind CSS from its CDN.

Choose a map layer for monthly moisture, USDA soil texture, USDA Soil Taxonomy
great group, or a numeric SoilGrids property. Numeric layers have an adjustable
colour range and a labelled legend; enter GPS coordinates to inspect the actual
selected-layer value at that point. You can also click anywhere on the map to
show that layer's value in a popup; the clicked point respects active soil
filters. Texture, taxonomy, and numeric property filters apply to both the map
and the wettest-location table. Numeric properties include pH, clay, sand, silt,
organic carbon, bulk density, cation exchange capacity, and total nitrogen.
SoilGrids values are static 0-5 cm estimates;
texture and taxonomy are static OpenLandMap 250 m predictions.
Numeric layers are converted to the displayed units. Soil property estimates
come from SoilGrids/ISRIC; categorical layers use
[OpenLandMap USDA texture](https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_TEXTURE-CLASS_USDA-TT_M_v02)
and
[USDA great-group taxonomy](https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_GRTGROUP_USDA-SOILTAX_C_v01)
(CC-BY-SA 4.0).

The map opens to the whole country. Optional GPS coordinates zoom to a point and
enable its daily readings. The selected month also produces a table of the 10
wettest ERA5-Land grid cells within the selected area, with state, GPS
coordinates, nearest GAUL district, soil texture, USDA taxonomy, and numeric
soil properties. An annual wetness-threshold slider ranks those same filtered
locations by the percentage of available daily readings in the selected year
at or above the chosen moisture value. Both tables can be downloaded as CSV.
These are modelled grid locations, not sensor sites. The map moisture-range
slider changes the colour scale, not the underlying table ranking or daily
readings.

The Pearson correlation heatmap compares monthly moisture with the numeric soil
properties at the ERA5-Land grid scale across valid cells in the selected area
and month, after applying the soil filters. Cell values are displayed on the
heatmap; blue indicates negative and red positive correlation. It is not
calculated from only the wettest 10 locations. Categorical texture and taxonomy
are excluded from Pearson correlation. The heatmap can also be downloaded as CSV.

Groq answers from the current selection, top-location values, correlations, and
the selected GPS-point value when present. Submitting a chat message sends the
question and this summary to Groq; GPS coordinates and source code are omitted.
Chat remains disabled until `GROQ_API_KEY` is configured.

Use the area dropdown to zoom and filter the map and ranked tables to all
Malaysia, Semenanjung Malaysia, Sabah & Sarawak, or an individual state/federal
territory. Entering GPS coordinates overrides the map zoom while the area
selection continues to filter the rankings.

If Earth Engine is not configured, the page still displays the basemap and
coordinate controls but does not invent soil data.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```
