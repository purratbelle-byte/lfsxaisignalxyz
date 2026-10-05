"""OTCharts read-only market-data adapter.

Quotex itself has no public official API. This adapter uses an external
read-only data API; the broker login/session is never stored here.
"""
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx

SUPPORTED_SYMBOLS = {"USD/MXN OTC", "USD/PKR OTC", "EUR/CHF OTC"}
DEFAULT_SYMBOL_IDS = {
    "USD/MXN OTC": "USDMXN_otc",
    "USD/PKR OTC": "USDPKR_otc",
    "EUR/CHF OTC": "EURCHF_otc",
}

@dataclass
class Tick:
    symbol: str
    timestamp: datetime
    price: float

class LiveDataProvider:
    def __init__(self):
        self.base_url = os.getenv("MARKET_DATA_API_BASE_URL", "https://otcharts.com").rstrip("/")
        self.api_key = os.getenv("MARKET_DATA_API_KEY", "")
        self.venue = os.getenv("MARKET_DATA_VENUE", "quotex")
        self.timeout = float(os.getenv("MARKET_DATA_TIMEOUT", "20"))

    def configured(self) -> bool:
        return bool(self.api_key)

    def validate_symbol(self, symbol: str) -> None:
        if symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(f"Unsupported symbol: {symbol}")

    def _headers(self) -> dict:
        if not self.api_key:
            raise RuntimeError("MARKET_DATA_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.api_key}"}

    async def catalogue(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/symbols",
                params={"venue": self.venue},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json().get("symbols", [])

    async def resolve_symbol(self, display_symbol: str) -> str:
        self.validate_symbol(display_symbol)
        requested = DEFAULT_SYMBOL_IDS[display_symbol]
        symbols = await self.catalogue()
        ids = {x.get("symbol") for x in symbols}
        if requested in ids:
            return requested

        wanted = display_symbol.replace(" OTC", "").replace("/", "").upper()
        for item in symbols:
            sid = str(item.get("symbol", ""))
            name = str(item.get("name", "")).replace("/", "").replace(" ", "").upper()
            if wanted in sid.upper().replace("/", "") or wanted in name:
                return sid
        raise RuntimeError(f"{display_symbol} is not currently listed by venue={self.venue}")

    async def history(self, display_symbol: str, limit: int = 300) -> list[dict]:
        symbol_id = await self.resolve_symbol(display_symbol)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/v1/candles",
                params={"venue": self.venue, "symbol": symbol_id, "tf": 300, "limit": min(limit, 5000)},
                headers=self._headers(),
            )
            r.raise_for_status()
            payload = r.json()
            if payload.get("gaps", {}).get("runs", 0):
                # Do not silently train across missing bars.
                raise RuntimeError(f"Historical feed has gaps for {display_symbol}: {payload['gaps']}")
            return payload.get("candles", [])

    async def stream(self, display_symbols: list[str]) -> AsyncIterator[Tick]:
        if not self.configured():
            raise RuntimeError("Live provider is not configured")
        ids = [await self.resolve_symbol(s) for s in display_symbols]
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/v1/stream",
                params={"venue": self.venue, "symbol": ",".join(ids)},
                headers=self._headers(),
            ) as r:
                r.raise_for_status()
                current_symbol_map = {sid: name for sid, name in zip(ids, display_symbols)}
                event = None
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                        continue
                    if line.startswith("data:") and event == "tick":
                        data = line.split(":", 1)[1].strip()
                        try:
                            payload = __import__("json").loads(data)
                            sid = payload["symbol"]
                            price = float(payload["price"])
                            ts = datetime.fromtimestamp(float(payload["time"]), tz=timezone.utc)
                            if sid in current_symbol_map:
                                yield Tick(current_symbol_map[sid], ts, price)
                        except (KeyError, TypeError, ValueError):
                            continue
