# Simple Routing Engine (GraphHopper + GTFS + OSM) — Magdeburg

This project is a small local routing setup using the **GraphHopper** engine to build a graph from:

- **OSM extract (`.pbf`)** for the street network
- **Local GTFS** public transport data (Magdeburg in our case with dates 2025-10-10 to 2026-10-09)

After the graph is built and stored locally, a Python CLI provides an interactive terminal where you enter coordinates (lon,lat) for **from** and **to** to generate itineraries.

---

## What this does

1. Starts GraphHopper with a config file (`config.yml`)
2. Builds the routing graph using **OSM + GTFS** using this command (java -Xmx8g -jar graphhopper/graphhopper-web-10.0.jar server graphhopper/config.yml)
3. Stores the built graph locally (so no need to rebuild every time)
4. Runs a Python interactive terminal that:
   - asks for origin and destination as `lon,lat`
   - returns route itineraries (public transport / multimodal depending on config)

---

## Requirements

- Java (compatible with GraphHopper `10.0`)
- Python 3.9+ (recommended)
- Local files:
  - Magdeburg **GTFS feed**
  - Magdeburg (or relevant area) **OSM `.pbf` extract**
- GraphHopper Web JAR:
  - `graphhopper/graphhopper-web-10.0.jar`
- Config file:
  - `graphhopper/config.yml`

---

## Project structure 

```text
.
├── graphhopper/
│   ├── graphhopper-web-10.0.jar
│   ├── config.yml
├── data/
│   ├── magdeburg.osm.pbf
│   └── magdeburg.gtfs.zip
│   └── graph-cache/
├── src /
|   ├── agent.py
|   ├──graphhopper_client.py
|   ├── intermodal_router.py
|   ├── personalised_router.py
|   ├── router.py
|   ├── value_model.py
├── main.py                        # interactive routing terminal or json
└── README.md
