from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

@dataclass(frozen=True)
class Candle:
    symbol: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(self.high - self.low, 0.0)

    @property
    def upper_wick(self) -> float:
        return max(self.high - max(self.open, self.close), 0.0)

    @property
    def lower_wick(self) -> float:
        return max(min(self.open, self.close) - self.low, 0.0)

    @property
    def direction(self) -> str:
        if self.close > self.open: return "UP"
        if self.close < self.open: return "DOWN"
        return "DOJI"

    def features(self) -> dict:
        r = self.range or 1e-12
        return {
            "direction": self.direction,
            "body_pct": self.body / r,
            "upper_wick_pct": self.upper_wick / r,
            "lower_wick_pct": self.lower_wick / r,
            "range": self.range,
            "body": self.body,
        }

def build_5m_candle(symbol: str, open_time: datetime, prices: Iterable[tuple[datetime, float]]) -> Candle:
    points=list(prices)
    if not points:
        raise ValueError("No price points")
    values=[p[1] for p in points]
    if open_time.tzinfo is None:
        open_time=open_time.replace(tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        open_time=open_time,
        close_time=open_time,
        open=values[0],
        high=max(values),
        low=min(values),
        close=values[-1],
    )
