from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime

from candle_engine import Candle
from pattern_engine import analyze_last_three

app=FastAPI(title="LFS X AI Signal XYZ", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class CandleIn(BaseModel):
    symbol: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float

class AnalyzeRequest(BaseModel):
    candles: list[CandleIn] = Field(default_factory=list)

@app.get("/")
def root():
    return {"name":"LFS X AI Signal XYZ","status":"online","timeframe":"5m"}

@app.get("/health")
def health():
    return {"ok":True}

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    candles=[Candle(**c.model_dump()) for c in req.candles]
    return analyze_last_three(candles)
