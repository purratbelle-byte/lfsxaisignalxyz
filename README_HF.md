---
title: LFS X AI Signal XYZ
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# LFS X AI Signal XYZ

5-minute OTC market-data analytics and historical-pattern signal engine.

The backend uses a server-side read-only market-data API key. Never put the key in frontend code or GitHub files.

Required Space secret:
- `MARKET_DATA_API_KEY`

Optional variables:
- `MARKET_DATA_VENUE=quotex`
- `MARKET_DATA_API_BASE_URL=https://otcharts.com`
- `ALLOWED_ORIGINS=*`
