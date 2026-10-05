# LFS X AI Signal XYZ

5-minute candle signal analysis platform.

## Markets
- USD/MXN OTC
- USD/PKR OTC
- EUR/CHF OTC

## Core logic
The engine uses the last 3 completed 5-minute candles, converts their OHLC structure into normalized features, searches historical 3-candle patterns, and calculates the next-candle UP/DOWN distribution.

A signal is only produced when the historical sample is large enough.

## Project structure
- frontend/ — web UI
- backend/ — FastAPI + candle/pattern engines
- database/ — PostgreSQL/Supabase schema
- .env.example — server configuration template

## Important
This project is an analytical/probability tool. Historical frequency is not a guarantee of future results. Live OTC data must come from a legitimate provider and must not be mislabeled as OTC.
