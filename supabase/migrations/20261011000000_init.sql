create extension if not exists pgcrypto;

-- The single workcell this database describes.
create table cell (
  id text primary key default 'cell',
  network text not null,
  network_id text not null,
  explorer_url text not null,
  api_url text,
  operator_address text,
  treasury_address text,
  broker_address text,
  vault_id text,
  domain_id text,
  accepts jsonb not null default '[]'::jsonb,
  online boolean not null default false,
  updated_at timestamptz not null default now()
);

create table arms (
  role text primary key check (role in ('left', 'head', 'right')),
  board text,
  address text,
  did text,
  state text not null default 'offline',
  joints jsonb,
  health jsonb,
  health_score numeric,
  credential text not null default 'none',
  balance_drops bigint,
  debt_drops bigint not null default 0,
  jobs_done integer not null default 0,
  earned_drops bigint not null default 0,
  updated_at timestamptz not null default now()
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  instruction text not null,
  requester text,
  status text not null default 'requested',
  price_drops bigint,
  payer_address text,
  payment_tx text,
  escrow_tx text,
  escrow_sequence integer,
  condition text,
  worker_role text references arms(role),
  target jsonb,
  destination jsonb,
  before_image_url text,
  after_image_url text,
  verdict jsonb,
  release_tx text,
  settlement_tx text,
  teleop boolean not null default false,
  error text,
  finished_at timestamptz
);

create table bids (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  job_id uuid not null references jobs(id) on delete cascade,
  arm_role text not null references arms(role),
  price_drops bigint not null,
  reach_m numeric,
  health_score numeric,
  feasible boolean not null,
  reason text,
  won boolean not null default false
);

-- One feed for everything that happens: moves, decisions and ledger transactions alike.
create table events (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  job_id uuid references jobs(id) on delete cascade,
  arm_role text,
  kind text not null,
  message text not null,
  tx_hash text,
  explorer_url text,
  amount_drops bigint,
  meta jsonb
);

create table channels (
  id text primary key,
  created_at timestamptz not null default now(),
  job_id uuid references jobs(id) on delete cascade,
  operator_address text not null,
  amount_drops bigint not null,
  claimed_drops bigint not null default 0,
  seconds_driven numeric not null default 0,
  status text not null default 'open',
  open_tx text,
  close_tx text,
  closed_at timestamptz
);

create table loans (
  id text primary key,
  created_at timestamptz not null default now(),
  arm_role text not null references arms(role),
  principal_drops bigint not null,
  outstanding_drops bigint not null,
  interest_bps integer not null default 0,
  status text not null default 'active',
  open_tx text,
  last_payment_tx text,
  closed_at timestamptz
);

create table depositors (
  address text primary key,
  created_at timestamptz not null default now(),
  name text,
  domain text,
  verified boolean not null default false,
  credential_tx text,
  deposited_drops bigint not null default 0,
  shares text,
  deposit_tx text
);

create index events_job_id_idx on events (job_id);
create index events_created_at_idx on events (created_at desc);
create index jobs_created_at_idx on jobs (created_at desc);
create index bids_job_id_idx on bids (job_id);

create or replace function touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger cell_touch before update on cell for each row execute function touch_updated_at();
create trigger arms_touch before update on arms for each row execute function touch_updated_at();
create trigger jobs_touch before update on jobs for each row execute function touch_updated_at();

alter publication supabase_realtime add table cell, arms, jobs, bids, events, channels, loans, depositors;

alter table cell enable row level security;
alter table arms enable row level security;
alter table jobs enable row level security;
alter table bids enable row level security;
alter table events enable row level security;
alter table channels enable row level security;
alter table loans enable row level security;
alter table depositors enable row level security;

create policy "cell is public" on cell for select using (true);
create policy "arms are public" on arms for select using (true);
create policy "jobs are public" on jobs for select using (true);
create policy "bids are public" on bids for select using (true);
create policy "events are public" on events for select using (true);
create policy "channels are public" on channels for select using (true);
create policy "loans are public" on loans for select using (true);
create policy "depositors are public" on depositors for select using (true);

insert into storage.buckets (id, name, public) values ('captures', 'captures', true);
create policy "captures are public" on storage.objects for select using (bucket_id = 'captures');
