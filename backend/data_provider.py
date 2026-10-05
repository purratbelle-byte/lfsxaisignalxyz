"""OTCharts read-only market-data adapter.

Quotex itself has no public official API. This adapter uses an external
read-only data API; broker login/session credentials are never stored here.
"""
import json
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
        self.base_url = os.getenv(
            "MARKET_DATA_API_BASE_URL", "https://otcharts.com"
        ).rstrip("/")
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
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "LFS-X-AI-Signal-XYZ/1.0",
        }

    async def _get_json(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def catalogue(self) -> list[dict]:
        payload = await self._get_json(
            "/v1/symbols", {"venue": self.venue}
        )
        return payload.get("symbols", [])

    async def usage(self) -> dict:
        return await self._get_json("/v1/usage")

    async def venues(self) -> list[dict]:
        payload = await self._get_json("/v1/venues")
        return payload.get("venues", [])

    async def diagnostics(self) -> dict:
        if not self.configured():
            return {
                "configured": False,
                "status": "SETUP_REQUIRED",
                "venue": self.venue,
            }

        usage = await self.usage()
        venues = await self.venues()
        selected = next(
            (v for v in venues if v.get("id") == self.venue), None
        )
        streams = usage.get("streams") or {}
        return {
            "configured": True,
            "status": "OK",
            "venue": self.venue,
            "plan": usage.get("planName") or usage.get("plan"),
            "books": usage.get("books", []),
            "venue_open": bool(selected and selected.get("open")),
            "venue_timeframes": (selected or {}).get("timeframes", []),
            "requests": usage.get("requests", {}),
            "streams": streams,
        }

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
            name = (
                str(item.get("name", ""))
                .replace("/", "")
                .replace(" ", "")
                .upper()
            )
            normalized_sid = sid.upper().replace("/", "")
            if wanted in normalized_sid or wanted in name:
                return sid

        raise RuntimeError(
            f"{display_symbol} is not currently listed by venue={self.venue}"
        )

    async def history(self, display_symbol: str, limit: int = 5000) -> list[dict]:
        symbol_id = await self.resolve_symbol(display_symbol)
        payload = await self._get_json(
            "/v1/candles",
            {
                "venue": self.venue,
                "symbol": symbol_id,
                "tf": 300,
                "limit": min(limit, 5000),
            },
        )
        if payload.get("gaps", {}).get("runs", 0):
            raise RuntimeError(
                f"Historical feed has gaps for {display_symbol}: "
                f"{payload['gaps']}"
            )
        return payload.get("candles", [])

    async def stream(self, display_symbol: str) -> AsyncIterator[Tick]:
        """Open one SSE stream for one symbol.

        OTCharts multiplexes symbols on the Pocket Option OTC book, but
        Quotex and the other books use one symbol per connection.
        """
        symbol_id = await self.resolve_symbol(display_symbol)
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/v1/stream",
                params={"venue": self.venue, "symbol": symbol_id},
                headers=self._headers(),
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line.split(":", 1)[1].strip()
                    try:
                        payload = json.loads(data)
                        if payload.get("symbol") != symbol_id:
                            continue
                        price = float(payload["price"])
                        ts = datetime.fromtimestamp(
                            float(payload["time"]), tz=timezone.utc
                        )
                        yield Tick(display_symbol, ts, price)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
