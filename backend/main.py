import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
provider_state = {"status": "STARTING", "details": {}}
live_tasks = []


def _history_to_candles(symbol, rows):
    candles = []
    for row in rows:
        ts = datetime.fromtimestamp(float(row["time"]), tz=timezone.utc)
        candles.append(Candle(
            symbol=symbol,
            open_time=ts,
            close_time=ts + timedelta(seconds=300),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
        ))
    return sorted(candles, key=lambda x: x.open_time)


async def _load_history():
    for symbol in SUPPORTED_SYMBOLS:
        try:
            rows = await provider.history(symbol, limit=5000)
            now = datetime.now(timezone.utc)
            candles = [
                c for c in _history_to_candles(symbol, rows)
                if c.close_time <= now
            ][-5000:]
            completed[symbol] = candles
            print(
                f"[HISTORY] {symbol}: loaded {len(candles)} completed 5m candles",
                flush=True,
            )

            result = analyze_last_three(candles)
            latest[symbol] = {
                "symbol": symbol,
                "timeframe": "5m",
                "mode": "HISTORICAL",
                "updated_at": now.isoformat(),
                **result,
            }
        except Exception as exc:
            print(f"[HISTORY_ERROR] {symbol}: {exc}", flush=True)
            latest[symbol] = {
                "status": "DATA_ERROR",
                "symbol": symbol,
                "mode": "HISTORICAL",
                "error": str(exc),
            }


def _record_closed(symbol, closed):
    bucket = completed[symbol]
    if not bucket or closed.open_time > bucket[-1].open_time:
        bucket.append(closed)
        del bucket[:-5000]

    result = analyze_last_three(bucket)
    latest[symbol] = {
        "symbol": symbol,
        "timeframe": "5m",
        "mode": "LIVE",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }


async def _live_loop():
    symbols = sorted(SUPPORTED_SYMBOLS)
    while True:
        try:
            async for tick in provider.stream(symbols):
                closed = builder.add_tick(tick)
                if closed is not None:
                    _record_closed(tick.symbol, closed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[LIVE_RECONNECT] {exc}", flush=True)
            await asyncio.sleep(5)


async def _start_live_streams(diag=None):
    global live_tasks
    try:
        if diag is None:
            diag = await provider.diagnostics()

        provider_state["details"] = diag
        print(f"[PROVIDER] {diag}", flush=True)

        if diag.get("status") != "OK":
            provider_state["status"] = diag.get("status", "DATA_ERROR")
            return

        if not diag.get("venue_open"):
            provider_state["status"] = "VENUE_NOT_OPEN"
            return

        stream_info = diag.get("streams") or {}
        stream_limit = stream_info.get("limit")
        instruments_per_stream = stream_info.get("instrumentsPerStream")

        if isinstance(stream_limit, int) and stream_limit < 1:
            provider_state["status"] = "LIVE_STREAMING_UNAVAILABLE"
            print(
                "[PROVIDER] Live streaming unavailable on current plan",
                flush=True,
            )
            return

        if (
            isinstance(instruments_per_stream, int)
            and instruments_per_stream < len(SUPPORTED_SYMBOLS)
        ):
            provider_state["status"] = "STREAM_INSTRUMENT_CAPACITY_INSUFFICIENT"
            provider_state["required_instruments"] = len(SUPPORTED_SYMBOLS)
            provider_state["instruments_per_stream"] = instruments_per_stream
            return

        provider_state["status"] = "LIVE_STARTING"
        live_tasks = [asyncio.create_task(_live_loop())]
        provider_state["status"] = "LIVE_RUNNING"
    except Exception as exc:
        provider_state["status"] = "PROVIDER_ERROR"
        provider_state["details"] = {"error": str(exc)}
        print(f"[PROVIDER_ERROR] {exc}", flush=True)


@asynccontextmanager
async def lifespan(app):
    if not provider.configured():
        provider_state["status"] = "SETUP_REQUIRED"
        yield
        return

    # Check account/book/plan access BEFORE spending any candle requests.
    diag = await provider.diagnostics()

    # Use the live OTC catalogue so the app never depends on a stale pair ID.
    global SUPPORTED_SYMBOLS, completed, latest
    if diag.get("status") == "OK" and diag.get("venue_open"):
        try:
            live_markets = await provider.currency_otc_markets(limit=3)
            if live_markets:
                SUPPORTED_SYMBOLS = set(live_markets)
                completed = {symbol: [] for symbol in SUPPORTED_SYMBOLS}
                latest = {}
                print(
                    f"[MARKETS] Using live OTC currency pairs: {sorted(SUPPORTED_SYMBOLS)}",
                    flush=True,
                )
        except Exception as exc:
            print(f"[MARKETS] Catalogue selection failed; using defaults: {exc}", flush=True)
    provider_state["details"] = diag

    if diag.get("status") == "OK" and diag.get("venue_open"):
        await _load_history()
    elif diag.get("status") == "OK" and not diag.get("venue_open"):
        provider_state["status"] = "VENUE_NOT_OPEN"
        print(
            "[STARTUP] Venue is not open for this key/plan; skipping history.",
            flush=True,
        )
    else:
        provider_state["status"] = diag.get("status", "PROVIDER_ERROR")
        print(
            "[STARTUP] Provider access check failed; skipping history and live.",
            flush=True,
        )

    await _start_live_streams(diag)

    yield

    for task in live_tasks:
        task.cancel()
    if live_tasks:
        await asyncio.gather(*live_tasks, return_exceptions=True)


app = FastAPI(title="LFS X AI Signal XYZ", version="1.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return {
        "name": "LFS X AI Signal XYZ",
        "status": "online",
        "timeframe": "5m",
        "markets": sorted(SUPPORTED_SYMBOLS),
        "live_provider_configured": provider.configured(),
        "provider_status": provider_state["status"],
    }


@app.get("/api/info")
def info():
    return root()


@app.get("/api/provider-status")
def provider_status():
    return {"status": provider_state["status"], "details": provider_state["details"]}


@app.get("/health")
def health():
    return {
        "ok": True,
        "live_provider_configured": provider.configured(),
        "provider_status": provider_state["status"],
        "venue": provider.venue,
        "timeframe_seconds": 300,
        "historical_candles": {s: len(completed[s]) for s in SUPPORTED_SYMBOLS},
    }


@app.get("/api/markets")
def markets():
    return {"timeframe_seconds": 300, "markets": sorted(SUPPORTED_SYMBOLS)}


@app.get("/api/signal/{symbol}")
def signal(symbol: str):
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=404, detail="Unsupported market")

    if not provider.configured():
        return {
            "symbol": symbol,
            "status": "SETUP_REQUIRED",
            "reason": "Configure MARKET_DATA_API_KEY on the backend server",
        }

    data = latest.get(symbol)
    if data:
        if provider_state["status"] == "LIVE_STREAMING_UNAVAILABLE":
            data = {
                **data,
                "live_available": False,
                "note": (
                    "Historical 5m analysis is available; live streaming "
                    "is disabled on the current data plan."
                ),
            }
        elif provider_state["status"] == "BOOK_ACCESS_MISMATCH":
            data = {
                **data,
                "live_available": False,
                "note": provider_state["details"].get("message"),
            }
        return data

    return {
        "symbol": symbol,
        "status": provider_state["status"],
        "reason": "Waiting for provider access and historical/live data",
    }


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    candles = [Candle(**c.model_dump()) for c in req.candles]
    return analyze_last_three(candles)


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
