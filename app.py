from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AzureOpenAI
from dotenv import load_dotenv
import os
import requests
import re
import time

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Azure OpenAI setup
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-12-01-preview",
    azure_endpoint="https://selva-mcq499f7-eastus2.cognitiveservices.azure.com/"
)

OMDB_API_KEY = "196872fc"
WATCHMODE_API_KEY = os.getenv("WATCHMODE_API_KEY")

LANGUAGE_MAP = {
    "english": "English", "hindi": "Hindi", "tamil": "Tamil", "telugu": "Telugu",
    "french": "French", "german": "German", "korean": "Korean",
    "japanese": "Japanese", "spanish": "Spanish", "italian": "Italian", "chinese": "Chinese"
}

class MoodRequest(BaseModel):
    mood: str
    language: str

@app.post("/recommend")
def recommend_movies(req: MoodRequest):
    language = LANGUAGE_MAP.get(req.language.lower(), "English")
    prompt = (
        f"Suggest 5 movies based on the following mood:\n'{req.mood}'\n\n"
        f"The user prefers to watch movies in '{language}'.\n"
        f"Include movie title and a short 1-line summary for each."
    )

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "You are a movie recommendation expert."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )

    content = response.choices[0].message.content.strip()
    titles = extract_titles(content)

    results = []
    for title in titles:
        info = fetch_movie_info(title)
        if info:
            results.append(info)
    return {"recommendations": results}

def extract_titles(gpt_output):
    lines = gpt_output.split("\n")
    titles = []
    for line in lines:
        match = re.match(r"^\d+\.\s+(.+?)(?:\s+\(|$)", line.strip())
        if match:
            title = match.group(1).strip()
            titles.append(title)
    return titles

def fetch_movie_info(title):
    params = {
        "t": title,
        "apikey": OMDB_API_KEY,
        "r": "json"
    }
    try:
        res = requests.get("http://www.omdbapi.com/", params=params, timeout=10)
        data = res.json()
        if data.get("Response") != "True":
            return None

        watchmode_sources = get_streaming_platforms(title)

        return {
            "title": data.get("Title"),
            "year": data.get("Year"),
            "poster": data.get("Poster") if data.get("Poster") != "N/A" else None,
            "rating": data.get("imdbRating") if data.get("imdbRating") != "N/A" else "Not Rated",
            "plot": data.get("Plot") if data.get("Plot") != "N/A" else "No summary available.",
            "platforms": watchmode_sources
        }

    except Exception as e:
        print("Error:", e)
        return None

def get_streaming_platforms(title):
    try:
        search_url = f"https://api.watchmode.com/v1/search/"
        search_params = {
            "apiKey": WATCHMODE_API_KEY,
            "search_field": "name",
            "search_value": title
        }
        search_resp = requests.get(search_url, params=search_params, timeout=5)
        search_data = search_resp.json()

        if not search_data.get("title_results"):
            return []

        movie_id = search_data["title_results"][0]["id"]

        sources_url = f"https://api.watchmode.com/v1/title/{movie_id}/sources/"
        sources_params = {"apiKey": WATCHMODE_API_KEY}
        sources_resp = requests.get(sources_url, params=sources_params, timeout=5)
        sources_data = sources_resp.json()

        platforms = sorted(list({src["name"] for src in sources_data if src["type"] == "sub"}))
        return platforms

    except Exception as e:
        print(f"Watchmode Error: {e}")
        return []
