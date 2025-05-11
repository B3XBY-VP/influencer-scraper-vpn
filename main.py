"""
main.py · VPN-scraper micro-service
───────────────────────────────────
Exposes three protected endpoints:

  POST /scrape      {handle:str}          → latest-posts scrape (DEFAULT_POST_LIMIT)
  POST /deepScan    {handle:str}          → deep-scan scrape (DEEP_POST_LIMIT)
  POST /rotate                              → force Surfshark IP rotation

Requests must include an HTTP Bearer token that matches $SCRAPER_TOKEN.
No Firebase / Firestore — this file is ONLY for the DigitalOcean VPN box.
"""

import os
from typing import Dict

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from scraper.instagram_scraper import scrape
from scraper.deep_scraper   import deep_scrape
from vpn.rotate_ip          import rotate_ip

# ─── Auth token ──────────────────────────────────────────────────────────────
SCRAPER_TOKEN = os.getenv("SCRAPER_TOKEN")
if not SCRAPER_TOKEN:
    raise RuntimeError("SCRAPER_TOKEN env-var must be set")

auth_scheme = HTTPBearer()

def verify_token(creds: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    if creds.credentials != SCRAPER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/scrape", dependencies=[Depends(verify_token)])
async def api_scrape(body: Dict = Body(...)):
    handle = body.get("handle")
    if not handle:
        raise HTTPException(status_code=422, detail="handle required")
    return await scrape(handle)

@app.post("/deepScan", dependencies=[Depends(verify_token)])
async def api_deep_scan(body: Dict = Body(...)):
    handle = body.get("handle")
    if not handle:
        raise HTTPException(status_code=422, detail="handle required")
    return await deep_scrape(handle)

@app.post("/rotate", dependencies=[Depends(verify_token)])
def api_rotate():
    return {"ip": rotate_ip()}

# ─── Local run (`python main.py`) ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )




