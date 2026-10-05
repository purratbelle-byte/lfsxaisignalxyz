import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .candle_engine import Candle
from .candle_builder import CandleBuilder
from .data_provider import LiveDataProvider, SUPPORTED_SYMBOLS
from .pattern_engine import analyze_last_three

provider = LiveDataProvider()
builder = CandleBuilder()
completed = {symbol: [] for symbol in SUPPORTED_SYMBOLS}
latest = {}
live_task = None

def _history_to_candles(symbol, rows):
    candles = []
    for row in rows:
        ts = datetime.fromtimestamp(float(row["time"]), tz=timezone.utc)
        candles.append(Candle(symbol=symbol, open_time=ts, close_time=ts + timedelta(seconds=300),
                              open=float(row["open"]), high=float(row["high"]),
                              low=float(row["low"]), close=float(row["close"])))
    return sorted(candles, key=lambda x: x.open_time)

async def _load_history():
    for symbol in SUPPORTED_SYMBOLS:
        try:
            rows = await provider.history(symbol, limit=300)
            now = datetime.now(timezone.utc)\n            completed[symbol] = [c for c in _history_to_candles(symbol, rows) if c.close_time <= now][-5000:]
        except Exception as exc:
            latest[symbol] = {"status": "DATA_ERROR", "symbol": symbol, "error": str(exc)}

async def _live_loop():
    while True:
        try:
            async for tick in provider.stream(list(SUPPORTED_SYMBOLS)):
                closed = builder.add_tick(tick)
                if closed is None:
                    continue
                bucket = completed[tick.symbol]
                if not bucket or closed.open_time > bucket[-1].open_time:
                    bucket.append(closed)
                    del bucket[:-5000]
                result = analyze_last_three(bucket)
                latest[tick.symbol] = {"symbol": tick.symbol, "timeframe": "5m",
                                       "updated_at": datetime.now(timezone.utc).isoformat(), **result}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for symbol in SUPPORTED_SYMBOLS:
                latest[symbol] = {"status": "LIVE_RECONNECTING", "symbol": symbol, "error": str(exc)}
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app):
    global live_task
    if provider.configured():
        await _load_history()
        live_task = asyncio.create_task(_live_loop())
    yield
    if live_task:
        live_task.cancel()
        try:
            await live_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="LFS X AI Signal XYZ", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

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
    return {"name":"LFS X AI Signal XYZ","status":"online","timeframe":"5m",
            "markets":sorted(SUPPORTED_SYMBOLS),"live_provider_configured":provider.configured()}

@app.get("/health")
def health():
    return {"ok":True,"live_provider_configured":provider.configured(),
            "venue":provider.venue,"timeframe_seconds":300}

@app.get("/api/markets")
def markets():
    return {"timeframe_seconds":300,"markets":sorted(SUPPORTED_SYMBOLS)}

@app.get("/api/signal/{symbol}")
def signal(symbol: str):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=404, detail="Unsupported market")
    if not provider.configured():
        return {"symbol":symbol,"status":"SETUP_REQUIRED",
                "reason":"Configure MARKET_DATA_API_KEY on the backend server"}
    return latest.get(symbol, {"symbol":symbol,"status":"WAITING","reason":"Collecting live candles"})

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    candles=[Candle(**c.model_dump()) for c in req.candles]
    return analyze_last_three(candles)
