"""Provider adapter; credentials remain server-side."""
import os
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Tick:
    symbol: str
    timestamp: datetime
    price: float

SUPPORTED_SYMBOLS={"USD/MXN OTC","USD/PKR OTC","EUR/CHF OTC"}

class LiveDataProvider:
    def __init__(self):
        self.url=os.getenv("MARKET_DATA_WS_URL","")
        self.api_key=os.getenv("MARKET_DATA_API_KEY","")
    def configured(self): return bool(self.url and self.api_key)
    def validate_symbol(self,symbol):
        if symbol not in SUPPORTED_SYMBOLS: raise ValueError("Unsupported symbol")
    async def stream(self):
        if not self.configured(): raise RuntimeError("Live provider is not configured")
        raise NotImplementedError("Add the selected documented OTC provider mapping here")
