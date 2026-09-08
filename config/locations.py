"""
config/locations.py — LANDSIGHT Multi-AOI and Location Registry
===============================================================
Defines the hierarchical geographic catalog for LANDSIGHT:
  State -> District -> Place / Suburb / Town

Distinguishes between:
  1. Actively Supported AOIs (with real calibrated 100m grid, DEM, rainfall & road graph)
  2. Selectable / Searchable regions outside active monitoring coverage (supported: False)

Designed for multi-AOI expansion: adding a new AOI only requires registering its
metadata and bounding box here.
"""

from __future__ import annotations
from typing import Optional, TypedDict

class Place(TypedDict, total=False):
    name: str
    lat: float
    lon: float
    place_type: str
    supported: bool
    aoi_id: Optional[str]

class District(TypedDict):
    name: str
    supported: bool
    aoi_id: Optional[str]
    center: list[float]  # [lon, lat]
    places: list[Place]

class State(TypedDict):
    name: str
    supported: bool  # True if at least one district has active coverage
    districts: list[District]

# ── Active AOI definitions ───────────────────────────────────────────────────
SUPPORTED_AOIS = {
    "guwahati_shillong_nh6": {
        "id": "guwahati_shillong_nh6",
        "name": "Guwahati–Shillong NH-6 Corridor",
        "description": "70 × 80 km corridor spanning Kamrup Metropolitan (Assam) and Ri-Bhoi / East Khasi Hills (Meghalaya). 100m calibrated inference grid.",
        "bbox": [91.40, 25.55, 92.20, 26.20],  # [min_lon, min_lat, max_lon, max_lat]
        "center": [91.82, 25.92],
        "default_zoom": 9.5,
        "primary_highway": "NH-6",
        "states": ["Assam", "Meghalaya"],
    }
}

# ── Hierarchical location registry ───────────────────────────────────────────
LOCATION_CATALOG: list[State] = [
    {
        "name": "Assam",
        "supported": True,
        "districts": [
            {
                "name": "Kamrup Metropolitan",
                "supported": True,
                "aoi_id": "guwahati_shillong_nh6",
                "center": [91.75, 26.15],
                "places": [
                    {"name": "Guwahati", "lat": 26.1445, "lon": 91.7362, "place_type": "city", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Dispur", "lat": 26.1415, "lon": 91.7900, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Jorabat", "lat": 26.0993, "lon": 91.8773, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Sonapur", "lat": 26.1192, "lon": 91.9702, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "North Guwahati", "lat": 26.1915, "lon": 91.7184, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Jalukbari", "lat": 26.1555, "lon": 91.6712, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Maligaon", "lat": 26.1600, "lon": 91.6958, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Kamakhya Dham", "lat": 26.1664, "lon": 91.7064, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Fancy Bazaar", "lat": 26.1799, "lon": 91.7362, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Pan Bazar", "lat": 26.1853, "lon": 91.7473, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Chandmari", "lat": 26.1841, "lon": 91.7741, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Noonmati", "lat": 26.1979, "lon": 91.7999, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Sualkuchi", "lat": 26.1699, "lon": 91.5709, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Amingaon", "lat": 26.1833, "lon": 91.6833, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Ganeshguri", "lat": 26.1490, "lon": 91.7837, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Satgaon", "lat": 26.1589, "lon": 91.8386, "place_type": "suburb", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                ],
            },
            {
                "name": "Kamrup Rural",
                "supported": False,
                "aoi_id": None,
                "center": [91.50, 26.30],
                "places": [
                    {"name": "Chaygaon", "lat": 26.050, "lon": 91.416, "place_type": "town", "supported": False, "aoi_id": None},
                    {"name": "Rangia", "lat": 26.470, "lon": 91.630, "place_type": "town", "supported": False, "aoi_id": None},
                    {"name": "Hajo", "lat": 26.250, "lon": 91.530, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
            {
                "name": "Cachar (Barak Valley)",
                "supported": False,
                "aoi_id": None,
                "center": [92.80, 24.83],
                "places": [
                    {"name": "Silchar", "lat": 24.833, "lon": 92.779, "place_type": "city", "supported": False, "aoi_id": None},
                ],
            },
            {
                "name": "Dibrugarh",
                "supported": False,
                "aoi_id": None,
                "center": [94.91, 27.47],
                "places": [
                    {"name": "Dibrugarh", "lat": 27.472, "lon": 94.912, "place_type": "city", "supported": False, "aoi_id": None},
                ],
            },
        ],
    },
    {
        "name": "Meghalaya",
        "supported": True,
        "districts": [
            {
                "name": "Ri-Bhoi",
                "supported": True,
                "aoi_id": "guwahati_shillong_nh6",
                "center": [91.87, 25.90],
                "places": [
                    {"name": "Nongpoh", "lat": 25.9036, "lon": 91.8805, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Byrnihat", "lat": 26.0543, "lon": 91.8696, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Umsning", "lat": 25.7500, "lon": 91.9000, "place_type": "town", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Barapani (Umiam)", "lat": 25.6600, "lon": 91.9100, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Umroi", "lat": 25.7000, "lon": 91.9800, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Umling", "lat": 25.9500, "lon": 91.8500, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                ],
            },
            {
                "name": "East Khasi Hills",
                "supported": True,
                "aoi_id": "guwahati_shillong_nh6",
                "center": [91.89, 25.57],
                "places": [
                    {"name": "Shillong", "lat": 25.5788, "lon": 91.8933, "place_type": "city", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Mawryngkneng", "lat": 25.5600, "lon": 92.0500, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Mawkasiang", "lat": 25.6000, "lon": 91.9500, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Mawpdang", "lat": 25.6100, "lon": 91.9600, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                    {"name": "Tynring", "lat": 25.5900, "lon": 91.9700, "place_type": "village", "supported": True, "aoi_id": "guwahati_shillong_nh6"},
                ],
            },
            {
                "name": "West Garo Hills",
                "supported": False,
                "aoi_id": None,
                "center": [90.22, 25.51],
                "places": [
                    {"name": "Tura", "lat": 25.514, "lon": 90.220, "place_type": "city", "supported": False, "aoi_id": None},
                ],
            },
            {
                "name": "East Jaintia Hills",
                "supported": False,
                "aoi_id": None,
                "center": [92.36, 25.33],
                "places": [
                    {"name": "Khliehriat", "lat": 25.333, "lon": 92.367, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
        ],
    },
    {
        "name": "Sikkim",
        "supported": False,
        "districts": [
            {
                "name": "Gangtok (East Sikkim)",
                "supported": False,
                "aoi_id": None,
                "center": [88.61, 27.33],
                "places": [
                    {"name": "Gangtok", "lat": 27.3314, "lon": 88.6138, "place_type": "city", "supported": False, "aoi_id": None},
                    {"name": "Singtam", "lat": 27.2340, "lon": 88.4980, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
            {
                "name": "Mangan (North Sikkim)",
                "supported": False,
                "aoi_id": None,
                "center": [88.52, 27.50],
                "places": [
                    {"name": "Mangan", "lat": 27.508, "lon": 88.527, "place_type": "town", "supported": False, "aoi_id": None},
                    {"name": "Chungthang", "lat": 27.604, "lon": 88.647, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
        ],
    },
    {
        "name": "Himachal Pradesh",
        "supported": False,
        "districts": [
            {
                "name": "Shimla",
                "supported": False,
                "aoi_id": None,
                "center": [77.17, 31.10],
                "places": [
                    {"name": "Shimla", "lat": 31.1048, "lon": 77.1734, "place_type": "city", "supported": False, "aoi_id": None},
                    {"name": "Rampur", "lat": 31.4480, "lon": 77.6320, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
            {
                "name": "Kullu",
                "supported": False,
                "aoi_id": None,
                "center": [77.10, 31.95],
                "places": [
                    {"name": "Manali", "lat": 32.2432, "lon": 77.1892, "place_type": "town", "supported": False, "aoi_id": None},
                    {"name": "Kullu", "lat": 31.9579, "lon": 77.1095, "place_type": "city", "supported": False, "aoi_id": None},
                ],
            },
        ],
    },
    {
        "name": "Uttarakhand",
        "supported": False,
        "districts": [
            {
                "name": "Chamoli",
                "supported": False,
                "aoi_id": None,
                "center": [79.35, 30.40],
                "places": [
                    {"name": "Joshimath", "lat": 30.5568, "lon": 79.5664, "place_type": "town", "supported": False, "aoi_id": None},
                    {"name": "Gopeshwar", "lat": 30.4136, "lon": 79.3242, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
            {
                "name": "Rudraprayag",
                "supported": False,
                "aoi_id": None,
                "center": [78.98, 30.28],
                "places": [
                    {"name": "Rudraprayag", "lat": 30.2844, "lon": 78.9811, "place_type": "town", "supported": False, "aoi_id": None},
                ],
            },
        ],
    },
]


def check_coords_in_aoi(lon: float, lat: float, aoi_id: str = "guwahati_shillong_nh6") -> bool:
    """Returns True if (lon, lat) falls within the active bounding box."""
    aoi = SUPPORTED_AOIS.get(aoi_id)
    if not aoi:
        return False
    min_lon, min_lat, max_lon, max_lat = aoi["bbox"]
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def search_locations(query: str, limit: int = 15) -> list[dict]:
    """
    Search catalog places, districts, states, and major supported highways.
    Returns matched items with coordinates, supported flag, and context.
    """
    q = query.strip().lower()
    if not q:
        return []

    results = []

    # 1. Search places
    for state in LOCATION_CATALOG:
        for dist in state["districts"]:
            for place in dist.get("places", []):
                p_name = place["name"]
                if q in p_name.lower():
                    results.append({
                        "type": "place",
                        "name": p_name,
                        "display_name": f"{p_name}, {dist['name']}, {state['name']}",
                        "place_type": place.get("place_type", "town"),
                        "state": state["name"],
                        "district": dist["name"],
                        "lat": place["lat"],
                        "lon": place["lon"],
                        "supported": place.get("supported", False),
                        "aoi_id": place.get("aoi_id"),
                    })

    # 2. Search districts
    for state in LOCATION_CATALOG:
        for dist in state["districts"]:
            d_name = dist["name"]
            if q in d_name.lower():
                results.append({
                    "type": "district",
                    "name": d_name,
                    "display_name": f"{d_name} (District), {state['name']}",
                    "place_type": "district",
                    "state": state["name"],
                    "district": d_name,
                    "lat": dist["center"][1],
                    "lon": dist["center"][0],
                    "supported": dist.get("supported", False),
                    "aoi_id": dist.get("aoi_id"),
                })

    # 3. Search states
    for state in LOCATION_CATALOG:
        s_name = state["name"]
        if q in s_name.lower():
            # Use center of first district
            first_dist = state["districts"][0]
            results.append({
                "type": "state",
                "name": s_name,
                "display_name": f"{s_name} (State)",
                "place_type": "state",
                "state": s_name,
                "district": first_dist["name"],
                "lat": first_dist["center"][1],
                "lon": first_dist["center"][0],
                "supported": state.get("supported", False),
                "aoi_id": first_dist.get("aoi_id"),
            })

    # Deduplicate by display_name
    seen = set()
    deduped = []
    for r in results:
        if r["display_name"] not in seen:
            seen.add(r["display_name"])
            deduped.append(r)

    # Sort supported first, then alphabetical
    deduped.sort(key=lambda x: (not x["supported"], x["display_name"]))
    return deduped[:limit]
