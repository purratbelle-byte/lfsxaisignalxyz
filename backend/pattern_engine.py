from collections import Counter
from dataclasses import dataclass
from .candle_engine import Candle

@dataclass
class PatternStats:
    pattern_id: str
    matches: int
    up: int
    down: int

    @property
    def up_probability(self) -> float:
        return self.up / self.matches * 100 if self.matches else 0.0

    @property
    def down_probability(self) -> float:
        return self.down / self.matches * 100 if self.matches else 0.0

    @property
    def confidence(self) -> str:
        if self.matches < 20: return "NO_SIGNAL"
        if self.matches < 50: return "LOW_SAMPLE"
        if self.matches < 100: return "NORMAL"
        return "STRONG_SAMPLE"

def candle_token(c: Candle) -> str:
    f=c.features()
    body="S" if f["body_pct"] < .25 else "M" if f["body_pct"] < .60 else "L"
    wick="U" if f["upper_wick_pct"] > .30 else "u"
    low="D" if f["lower_wick_pct"] > .30 else "d"
    return f"{f['direction'][0]}{body}{wick}{low}"

def pattern_id(candles: list[Candle]) -> str:
    if len(candles) != 3:
        raise ValueError("Exactly 3 completed candles are required")
    return "-".join(candle_token(c) for c in candles)

def find_historical_matches(history: list[Candle], current: list[Candle]) -> PatternStats:
    pid=pattern_id(current)
    up=down=0
    matches=0
    for i in range(2, len(history)-1):
        window=history[i-2:i+1]
        if pattern_id(window) != pid:
            continue
        next_candle=history[i+1]
        if next_candle.close > next_candle.open: up += 1
        elif next_candle.close < next_candle.open: down += 1
        else: continue
        matches += 1
    return PatternStats(pid, matches, up, down)

def analyze_last_three(history: list[Candle]) -> dict:
    if len(history) < 4:
        return {"status":"WAITING","reason":"Need at least 4 completed candles"}
    current=history[-3:]
    stats=find_historical_matches(history[:-1], current)
    return {
        "status": stats.confidence,
        "pattern_id": stats.pattern_id,
        "matches": stats.matches,
        "up": stats.up,
        "down": stats.down,
        "up_probability": round(stats.up_probability,2),
        "down_probability": round(stats.down_probability,2),
        "direction": "UP" if stats.up > stats.down else "DOWN" if stats.down > stats.up else "NEUTRAL",
    }
