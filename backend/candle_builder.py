from datetime import datetime, timezone
from .candle_engine import Candle

class CandleBuilder:
    timeframe_seconds=300
    def __init__(self): self._state={}
    def bucket_start(self,ts):
        ts=ts.astimezone(timezone.utc); epoch=int(ts.timestamp())
        return datetime.fromtimestamp(epoch-(epoch%300),tz=timezone.utc)
    def add_tick(self,tick):
        bucket=self.bucket_start(tick.timestamp); key=(tick.symbol,bucket)
        if key not in self._state:
            self._state[key]={"open":tick.price,"high":tick.price,"low":tick.price,"close":tick.price}
            return None
        s=self._state[key]; s["high"]=max(s["high"],tick.price); s["low"]=min(s["low"],tick.price); s["close"]=tick.price
        return None
    def close_bucket(self,symbol,bucket):
        s=self._state.pop((symbol,bucket),None)
        if not s:return None
        return Candle(symbol=symbol,open_time=bucket,close_time=bucket,**s)
