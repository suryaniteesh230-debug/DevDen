from fastapi import FastAPI, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from dotenv import load_dotenv
import os
import json
import re
import requests
from math import radians, sin, cos, sqrt, atan2

load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_coordinates(place_name):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": place_name,
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "HeritageQuestAI"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers
    )

    data = response.json()

    if len(data) == 0:
        return None

    return {
        "lat": float(data[0]["lat"]),
        "lng": float(data[0]["lon"])
    }

def get_travel_time(origin, destination):

    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{origin['lng']},{origin['lat']};"
        f"{destination['lng']},{destination['lat']}"
        f"?overview=false"
    )

    response = requests.get(url)

    data = response.json()

    if (
        "routes" not in data
        or len(data["routes"]) == 0
    ):
        return float("inf")

    return data["routes"][0]["duration"]

def get_route_segment(origin, destination):

    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{origin['lng']},{origin['lat']};"
        f"{destination['lng']},{destination['lat']}"
        f"?overview=full&geometries=geojson"
    )

    response = requests.get(url)

    data = response.json()

    if (
        "routes" not in data
        or len(data["routes"]) == 0
    ):
        return {
            "duration": 0,
            "distance": 0,
            "geometry": []
        }

    route = data["routes"][0]

    duration_minutes = round(route["duration"] / 60)
    distance_km = round(route["distance"] / 1000, 1)
    geometry_coords = route["geometry"]["coordinates"]

    return {
        "duration": duration_minutes,
        "distance": distance_km,
        "geometry": geometry_coords
    }

def calculate_distance(lat1, lon1, lat2, lon2):

    R = 6371

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return R * c

def greedy_optimize(group):

    if len(group) <= 1:
        return group

    optimized = []

    # Start from southern-most point
    current = min(
        group,
        key=lambda x: x["lat"]
    )

    optimized.append(current)

    remaining = [
        place
        for place in group
        if place != current
    ]

    while remaining:

        nearest = min(
            remaining,
            key=lambda place:
                get_travel_time(
                    current,
                    place
                )
        )

        optimized.append(nearest)

        remaining.remove(nearest)

        current = nearest

    return optimized

@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    try:

        image_bytes = await file.read()

        model = genai.GenerativeModel(
            "models/gemini-2.5-flash"
        )

        response = model.generate_content(
            [
                {
                    "mime_type": file.content_type,
                    "data": image_bytes,
                },
                """
                Analyze this monument image.

                Return ONLY valid JSON.

                {
                  "monument": "",
                  "location": "",
                  "country": "",
                  "local_language": "",
                  "architecture_style": "",
                  "construction_year": "",
                  "historical_significance": "",
                  "interesting_fact": ""
                }

                Rules:
                - Return only JSON.
                - No markdown.
                - No explanation.
                - historical_significance should be 1-2 sentences.
                - interesting_fact should be 1 sentence.
                """
            ]
        )

        result_text = response.text.strip()

        # Remove markdown if Gemini adds it
        result_text = re.sub(r"```json|```", "", result_text).strip()

        monument_data = json.loads(result_text)

        return monument_data

    except Exception as e:
        return {
            "error": str(e)
        }

@app.post("/plan-trip")
async def plan_trip(data: dict = Body(...)):
    try:

        locations = data["locations"]

        prompt = f"""
        You are a heritage travel planner.

        For each location:

        1. Assign one slot:
        - Morning
        - Afternoon
        - Evening

        2. Assign priority:
        Morning = 1
        Afternoon = 2
        Evening = 3

        3. Give a short reason.

        Return ONLY valid JSON.

        Example:

        [
        {{
        "location":"Charminar",
        "slot":"Morning",
        "priority":1,
        "reason":"Cool temperatures and pleasant atmosphere."
        }}
        ]

        Locations:

        {locations}
        """

        model = genai.GenerativeModel(
            "models/gemini-2.5-flash"
        )

        response = model.generate_content(prompt)

        result = response.text.strip()

        result = re.sub(
            r"```json|```",
            "",
            result
        ).strip()

        trip_data = json.loads(result)

        # Add coordinates first
        for item in trip_data:

            coordinates = get_coordinates(
                item["location"]
            )

            if coordinates:

                item["lat"] = coordinates["lat"]
                item["lng"] = coordinates["lng"]

            else:

                item["lat"] = None
                item["lng"] = None

        # Then build groups
        morning = []
        afternoon = []
        evening = []

        for item in trip_data:

            if item["priority"] == 1:
                morning.append(item)

            elif item["priority"] == 2:
                afternoon.append(item)

            elif item["priority"] == 3:
                evening.append(item)

        # Now greedy can use coordinates
        morning = greedy_optimize(morning)
        afternoon = greedy_optimize(afternoon)
        evening = greedy_optimize(evening)

        optimized_route = (
            morning +
            afternoon +
            evening
        )

        for i in range(
            len(optimized_route) - 1
        ):

            current = optimized_route[i]

            next_stop = optimized_route[i + 1]

            travel_time = get_travel_time(
                current,
                next_stop
            )

            current["next_stop_minutes"] = round(
                travel_time / 60
            )

        optimized_route[-1][
            "next_stop_minutes"
        ] = None

        # Build road-following route segments using OSRM
        segments = []

        for i in range(len(optimized_route) - 1):

            origin = optimized_route[i]
            destination = optimized_route[i + 1]

            if (
                origin["lat"] is not None
                and origin["lng"] is not None
                and destination["lat"] is not None
                and destination["lng"] is not None
            ):
                segment = get_route_segment(origin, destination)
                segments.append(segment)

            else:
                segments.append({
                    "duration": 0,
                    "distance": 0,
                    "geometry": []
                })

        return {
            "optimized_route": optimized_route,
            "segments": segments
        }

    except Exception as e:
        return {
            "error": str(e)
        }