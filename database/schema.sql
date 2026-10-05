create table if not exists candles (
  id bigserial primary key,
  symbol text not null,
  timeframe_seconds integer not null default 300,
  open numeric not null,
  high numeric not null,
  low numeric not null,
  close numeric not null,
  open_time timestamptz not null,
  close_time timestamptz not null,
  created_at timestamptz not null default now(),
  unique(symbol, timeframe_seconds, open_time)
);

create index if not exists idx_candles_symbol_time
on candles(symbol, timeframe_seconds, open_time desc);

create table if not exists signals (
  id bigserial primary key,
  symbol text not null,
  candle_time timestamptz not null,
  pattern_id text not null,
  matches integer not null,
  up_count integer not null,
  down_count integer not null,
  up_probability numeric not null,
  down_probability numeric not null,
  confidence text not null,
  created_at timestamptz not null default now()
);
