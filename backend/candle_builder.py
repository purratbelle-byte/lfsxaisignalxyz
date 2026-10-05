from datetime import datetime, timezone, timedelta
from .candle_engine import Candle

class CandleBuilder:
    timeframe_seconds = 300

    def __init__(self):
        self._state = {}

    def bucket_start(self, ts: datetime) -> datetime:
        ts = ts.astimezone(timezone.utc)
        epoch = int(ts.timestamp())
        return datetime.fromtimestamp(
            epoch - (epoch % self.timeframe_seconds), tz=timezone.utc
        )

    def add_tick(self, tick):
        bucket = self.bucket_start(tick.timestamp)
        key = tick.symbol

        previous = self._state.get(key)
        if previous and bucket < previous["bucket"]:
            return None  # ignore late/out-of-order ticks

        if previous and bucket > previous["bucket"]:
            closed = self._emit(key, previous["bucket"])
            self._state[key] = {
                "bucket": bucket,
                "open": tick.price,
                "high": tick.price,
                "low": tick.price,
                "close": tick.price,
            }
            return closed

        if not previous:
            self._state[key] = {
                "bucket": bucket,
                "open": tick.price,
                "high": tick.price,
                "low": tick.price,
                "close": tick.price,
            }
            return None

        previous["high"] = max(previous["high"], tick.price)
        previous["low"] = min(previous["low"], tick.price)
        previous["close"] = tick.price
        return None

    def _emit(self, symbol, bucket):
        s = self._state.pop(symbol, None)
        if not s:
            return None
        return Candle(
            symbol=symbol,
            open_time=bucket,
            close_time=bucket + timedelta(seconds=self.timeframe_seconds),
            open=s["open"],
            high=s["high"],
            low=s["low"],
            close=s["close"],
        )
