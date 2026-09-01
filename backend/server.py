"""
Legged Studio Backend Server
Phase 0 - Task 0.1: Minimal FastAPI server for Electron communication test
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import sys

app = FastAPI(title="Legged Studio Backend", version="0.1.0")

# CORS for Electron renderer process
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Legged Studio Backend is running"}

@app.get("/health")
async def health():
    """Health check endpoint for Electron startup"""
    return {
        "status": "ok",
        "version": "0.1.0",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }

@app.get("/api/test")
async def test():
    """Test endpoint"""
    return {
        "message": "Hello from Legged Studio!",
        "phase": "Phase 0 - Task 0.1",
        "status": "success"
    }

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info"
    )
