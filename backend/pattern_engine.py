from dataclasses import dataclass
from .candle_engine import Candle

@dataclass
class PatternStats:
    pattern_id: str
    matches: int
    up: int
    down: int

    @property
    def up_probability(self):
        return self.up / self.matches * 100 if self.matches else 0.0

    @property
    def down_probability(self):
        return self.down / self.matches * 100 if self.matches else 0.0

    @property
    def confidence(self):
        if self.matches < 20:
            return "NO_SIGNAL"
        if self.matches < 50:
            return "LOW_SAMPLE"
        if self.matches < 100:
            return "NORMAL"
        return "STRONG_SAMPLE"

def candle_token(c: Candle) -> str:
    f = c.features()
    body = "S" if f["body_pct"] < .25 else "M" if f["body_pct"] < .60 else "L"
    upper = "H" if f["upper_wick_pct"] > .30 else "L"
    lower = "H" if f["lower_wick_pct"] > .30 else "L"
    return f"{f['direction'][0]}{body}U{upper}D{lower}"

def pattern_id(candles):
    if len(candles) != 3:
        raise ValueError("Exactly 3 completed candles are required")
    return "-".join(candle_token(c) for c in candles)

def _signature(c: Candle):
    f = c.features()
    return (
        1.0 if f["direction"] == "UP" else -1.0 if f["direction"] == "DOWN" else 0.0,
        f["body_pct"],
        f["upper_wick_pct"],
        f["lower_wick_pct"],
    )

def _distance(a, b):
    # Direction is important; the other values allow similar, not only identical, patterns.
    total = 0.0
    for x, y in zip(_signature(a), _signature(b)):
        total += 1.5 * abs(x - y) if x in (-1.0, 1.0) else abs(x - y)
    return total

def find_historical_matches(history, current, tolerance=0.95):
    pid = pattern_id(current)
    up = down = matches = 0
    for end in range(2, len(history) - 1):
        window = history[end - 2:end + 1]
        if len(window) != 3:
            continue
        distance = sum(_distance(a, b) for a, b in zip(window, current))
        if distance > tolerance:
            continue
        nxt = history[end + 1]
        if nxt.close > nxt.open:
            up += 1
            matches += 1
        elif nxt.close < nxt.open:
            down += 1
            matches += 1
    return PatternStats(pid, matches, up, down)

def analyze_last_three(completed):
    ordered = sorted(completed, key=lambda x: x.open_time)
    if len(ordered) < 7:
        return {"status": "WAITING", "reason": "Need more completed historical candles"}

    current = ordered[-3:]
    history = ordered[:-3]
    stats = find_historical_matches(history, current)

    return {
        "status": stats.confidence,
        "pattern_id": stats.pattern_id,
        "matches": stats.matches,
        "up": stats.up,
        "down": stats.down,
        "up_probability": round(stats.up_probability, 2),
        "down_probability": round(stats.down_probability, 2),
        "direction": (
            "UP" if stats.up > stats.down else
            "DOWN" if stats.down > stats.up else
            "NEUTRAL"
        ) if stats.matches >= 20 else "WAITING",
    }
