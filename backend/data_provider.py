"""OTCharts OTC (Pocket Option) read-only market-data adapter.

Uses the OTCharts `otc` book. Broker login/session credentials are never
stored here; only an OTCharts API key is used server-side.
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
        # OTCharts "otc" book = Pocket Option OTC feed.
        self.venue = os.getenv("MARKET_DATA_VENUE", "otc")
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
            "User-Agent": "LFS-X-AI-Signal-XYZ/1.2",
            "Accept": "application/json",
        }

    async def _get_json(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
            )
            if r.is_error:
                detail = r.text[:500].replace("\n", " ")
                raise RuntimeError(
                    f"OTCharts {r.status_code} on {path}: {detail}"
                )
            return r.json()

    async def catalogue(self) -> list[dict]:
        payload = await self._get_json(
            "/v1/symbols", {"venue": self.venue}
        )
        return payload.get("symbols", [])

    async def usage(self) -> dict:
        return await self._get_json("/v1/usage")

    async def currency_otc_markets(self, limit: int = 3) -> list[str]:
        """Return currently listed OTC currency-pair display names."""
        symbols = await self.catalogue()
        markets = []
        for item in symbols:
            name = str(item.get("name", "")).strip()
            sid = str(item.get("symbol", "")).strip()
            if not name or not sid:
                continue
            upper = name.upper()
            if not upper.endswith(" OTC"):
                continue
            pair = name[:-4].strip()
            if "/" not in pair:
                continue
            left, right = pair.split("/", 1)
            if len(left.strip()) != 3 or len(right.strip()) != 3:
                continue
            if not left.strip().isalpha() or not right.strip().isalpha():
                continue
            markets.append(name)
            if len(markets) >= limit:
                break
        return markets

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

        try:
            usage, venues = await asyncio_gather_usage_venues(self)
        except Exception as exc:
            return {
                "configured": True,
                "status": "PROVIDER_ERROR",
                "venue": self.venue,
                "error": str(exc),
            }

        selected = next(
            (v for v in venues if v.get("id") == self.venue), None
        )
        books = usage.get("books", [])
        streams = usage.get("streams") or {}
        access = self.venue in books

        result = {
            "configured": True,
            "status": "OK" if access else "BOOK_ACCESS_MISMATCH",
            "venue": self.venue,
            "plan": usage.get("planName") or usage.get("plan"),
            "books": books,
            "book_access": access,
            "venue_open": bool(selected and selected.get("open")),
            "venue_timeframes": (selected or {}).get("timeframes", []),
            "requests": usage.get("requests", {}),
            "streams": streams,
        }
        if not access:
            result["message"] = (
                f"API key does not open venue={self.venue}. "
                f"Key books are {books}. Create/select an OTCharts key "
                f"that opens the {self.venue} book."
            )
        return result

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

    async def stream(self, display_symbols: list[str]) -> AsyncIterator[Tick]:
        if not display_symbols:
            return

        symbol_map = {}
        for display_symbol in display_symbols:
            symbol_map[await self.resolve_symbol(display_symbol)] = display_symbol

        requested_ids = list(symbol_map)
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/v1/stream",
                params={
                    "venue": self.venue,
                    "symbol": ",".join(requested_ids),
                },
                headers=self._headers(),
            ) as r:
                r.raise_for_status()

                subscribed_ids = set(requested_ids)
                event_type = None

                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        continue

                    if not line.startswith("data:"):
                        continue

                    data = line.split(":", 1)[1].strip()
                    try:
                        payload = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if event_type == "connected":
                        connected = payload.get("symbols") or []
                        subscribed_ids = set(connected)
                        event_type = None
                        continue

                    symbol_id = payload.get("symbol")
                    if symbol_id not in subscribed_ids:
                        event_type = None
                        continue

                    try:
                        price = float(payload["price"])
                        ts = datetime.fromtimestamp(
                            float(payload["time"]), tz=timezone.utc
                        )
                    except (KeyError, TypeError, ValueError):
                        event_type = None
                        continue

                    yield Tick(symbol_map[symbol_id], ts, price)
                    event_type = None


async def asyncio_gather_usage_venues(provider: LiveDataProvider):
    import asyncio
    return await asyncio.gather(provider.usage(), provider.venues())
