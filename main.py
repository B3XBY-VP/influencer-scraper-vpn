# backend/main.py

import os
import json
import requests
import uvicorn

from fastapi import FastAPI, HTTPException, Query, Path, Body
from fastapi.middleware.cors import CORSMiddleware

from firebase_admin import credentials, initialize_app, firestore

# ──────────────────────────────────────────────────────────────────────────────
# 1) Firestore initialization via JSON‐in‐env
# ──────────────────────────────────────────────────────────────────────────────
sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not sa_json:
    raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON env var")
cred = credentials.Certificate(json.loads(sa_json))
initialize_app(cred)
db = firestore.client()

# ──────────────────────────────────────────────────────────────────────────────
# 2) Scraper-VPN service configuration
# ──────────────────────────────────────────────────────────────────────────────
SCRAPER_URL = os.getenv("SCRAPER_URL")
if not SCRAPER_URL:
    raise RuntimeError("Missing SCRAPER_URL env var")
SCRAPER_TOKEN = os.getenv("SCRAPER_TOKEN")
if not SCRAPER_TOKEN:
    raise RuntimeError("Missing SCRAPER_TOKEN env var")

from config import DEEP_SCAN_PASSWORD

app = FastAPI()

# CORS (lock this down in prod!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# 1) GET /api/scrape?handle=...
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/scrape")
async def api_scrape(handle: str = Query(..., description="Instagram handle")):
    resp = requests.post(
        f"{SCRAPER_URL}/scrape",
        json={"handle": handle},
        headers={"Authorization": f"Bearer {SCRAPER_TOKEN}"}
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    db.collection("creators").document(handle).set(
        {**data, "handle": handle, "lastChecked": firestore.SERVER_TIMESTAMP},
        merge=True,
    )
    return data

# ──────────────────────────────────────────────────────────────────────────────
# 2) GET /api/deepScan?handle=...&pw=...
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/api/deepScan")
async def api_deep_scan(
    handle: str = Query(..., description="Instagram handle"),
    pw: str = Query(None, description="Deep-scan password"),
):
    if pw != DEEP_SCAN_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid deep-scan password")
    resp = requests.post(
        f"{SCRAPER_URL}/deepScan",
        json={"handle": handle},
        headers={"Authorization": f"Bearer {SCRAPER_TOKEN}"}
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    db.collection("creators").document(handle).set(
        {**data, "handle": handle, "lastChecked": firestore.SERVER_TIMESTAMP},
        merge=True,
    )
    return data

# ──────────────────────────────────────────────────────────────────────────────
# 3) POST /api/recheck/{id}
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/recheck/{id}")
async def api_recheck(id: str = Path(..., description="Creator document ID")):
    doc = db.collection("creators").document(id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Creator not found")
    handle = doc.to_dict().get("handle")
    resp = requests.post(
        f"{SCRAPER_URL}/scrape",
        json={"handle": handle},
        headers={"Authorization": f"Bearer {SCRAPER_TOKEN}"}
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    db.collection("creators").document(id).update(
        {**data, "lastChecked": firestore.SERVER_TIMESTAMP}
    )
    return {"status": "ok"}

# ──────────────────────────────────────────────────────────────────────────────
# 4) POST /api/deepScan/{id}
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/deepScan/{id}")
async def api_deep_recheck(id: str = Path(..., description="Creator document ID")):
    doc = db.collection("creators").document(id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Creator not found")
    handle = doc.to_dict().get("handle")
    resp = requests.post(
        f"{SCRAPER_URL}/deepScan",
        json={"handle": handle},
        headers={"Authorization": f"Bearer {SCRAPER_TOKEN}"}
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    db.collection("creators").document(id).update(
        {**data, "lastChecked": firestore.SERVER_TIMESTAMP}
    )
    return {"status": "ok"}

# ──────────────────────────────────────────────────────────────────────────────
# 5–7) Burner account endpoints (unchanged)
# ──────────────────────────────────────────────────────────────────────────────
from bot.burner_login import login_and_store, refresh_session

@app.get("/api/burners")
async def list_burners():
    docs = db.collection("burners").stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]

@app.post("/api/burners")
async def add_burner(body: dict = Body(...)):
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Both username and password are required")
    doc_ref = db.collection("burners").document()
    doc_ref.set({"username": username, "password": password, "status": "pending"})
    asyncio.create_task(login_and_store(doc_ref.id, username, password))
    return {"id": doc_ref.id}

@app.post("/api/burners/{id}/refresh")
async def refresh_burner(id: str = Path(..., description="Burner document ID")):
    doc = db.collection("burners").document(id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Burner not found")
    data = doc.to_dict()
    session = refresh_session(id, data["username"], data["password"])
    return {"session": session}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)



