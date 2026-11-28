create schema if not exists poker;

create schema if not exists auth;

-- The emails that may make an account, and whose account each is.
create table if not exists poker.player (
    email text primary key constraint player_email_lowercase check (email = lower(email)),
    kind text not null default 'person' check (kind in ('person', 'internal', 'test')),
    added_at timestamptz not null default now()
);

-- A room is a code players share. Each of its hands is a session. A room with a
-- buy-in plays for chips: each seat's stack is chips moved from the player's
-- account to the room's account (`room:<code>`), carried from hand to hand.
create table if not exists poker.room (
    code text primary key check (code ~ '^[A-HJ-NP-Z2-9]{6}$'),
    buy_in bigint check (buy_in > 0),
    created_at timestamptz not null default now()
);

create table if not exists poker.session (
    id text primary key check (id ~ '^[0-9a-f]{16}$'),
    code text not null constraint session_code_room references poker.room on delete cascade,
    game text not null,
    parameters jsonb not null,
    seed bigint not null,
    chance_policy text not null,
    created_at timestamptz not null default now(),
    finished_at timestamptz,
    returns double precision[],
    check ((finished_at is null) = (returns is null))
);

create index if not exists session_created_at on poker.session (created_at desc);
create index if not exists session_finished_at on poker.session (finished_at desc)
    where finished_at is not null;
create index if not exists session_code on poker.session (code, created_at desc);

create table if not exists poker.seat (
    session_id text not null references poker.session on delete cascade,
    seat smallint not null check (seat >= 0),
    controller text not null,
    config jsonb not null,
    autoplay boolean not null,
    player text,
    primary key (session_id, seat)
);

create table if not exists poker.ply (
    session_id text not null references poker.session on delete cascade,
    ply integer not null check (ply >= 0),
    seat smallint check (seat >= 0),
    action integer not null,
    bot_output jsonb,
    primary key (session_id, ply)
);

-- Every chip there is: the treasury's opening balance is the whole supply, and
-- chips only move between accounts, so the balances always sum to it.
create table if not exists poker.account (
    id text primary key,
    balance bigint not null check (balance >= 0)
);

insert into poker.account (id, balance) values ('treasury', 1000000) on conflict do nothing;

create table if not exists poker.transfer (
    id bigint generated always as identity primary key,
    from_account text not null references poker.account,
    to_account text not null references poker.account,
    amount bigint not null check (amount > 0),
    reason text not null constraint transfer_reason
        check (reason in ('grant', 'buy_in', 'cash_out', 'purchase', 'reclaim')),
    created_at timestamptz not null default now()
);

create table if not exists poker.room_seat (
    code text not null references poker.room on delete cascade,
    player text not null,
    stack bigint not null check (stack >= 0),
    joined_at timestamptz not null default now(),
    primary key (code, player)
);
