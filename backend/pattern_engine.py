from dataclasses import dataclass
from .candle_engine import Candle

@dataclass
class PatternStats:
    pattern_id:str; matches:int; up:int; down:int
    @property
    def up_probability(self): return self.up/self.matches*100 if self.matches else 0.0
    @property
    def down_probability(self): return self.down/self.matches*100 if self.matches else 0.0
    @property
    def confidence(self):
        if self.matches<20:return "NO_SIGNAL"
        if self.matches<50:return "LOW_SAMPLE"
        if self.matches<100:return "NORMAL"
        return "STRONG_SAMPLE"

def candle_token(c):
    f=c.features(); body="S" if f["body_pct"]<.25 else "M" if f["body_pct"]<.60 else "L"
    return f"{f['direction'][0]}{body}{'U' if f['upper_wick_pct']>.30 else 'u'}{'D' if f['lower_wick_pct']>.30 else 'd'}"

def pattern_id(candles):
    if len(candles)!=3: raise ValueError("Exactly 3 completed candles are required")
    return "-".join(candle_token(c) for c in candles)

def find_historical_matches(history,current):
    pid=pattern_id(current); up=down=matches=0
    for end in range(2,len(history)-1):
        if pattern_id(history[end-2:end+1])!=pid: continue
        nxt=history[end+1]
        if nxt.close>nxt.open: up+=1; matches+=1
        elif nxt.close<nxt.open: down+=1; matches+=1
    return PatternStats(pid,matches,up,down)

def analyze_last_three(completed):
    if len(completed)<4:return {"status":"WAITING","reason":"Need historical candles"}
    ordered=sorted(completed,key=lambda x:x.open_time); current=ordered[-3:]; history=ordered[:-3]
    if len(history)<4:return {"status":"WAITING","reason":"Need more historical candles"}
    s=find_historical_matches(history,current)
    return {"status":s.confidence,"pattern_id":s.pattern_id,"matches":s.matches,"up":s.up,"down":s.down,
            "up_probability":round(s.up_probability,2),"down_probability":round(s.down_probability,2),
            "direction":("UP" if s.up>s.down else "DOWN" if s.down>s.up else "NEUTRAL") if s.matches>=20 else "WAITING"}
