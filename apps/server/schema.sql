create schema if not exists poker;

create table if not exists poker.session (
    id text primary key check (id ~ '^[0-9a-f]{16}$'),
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

create table if not exists poker.seat (
    session_id text not null references poker.session on delete cascade,
    seat smallint not null check (seat >= 0),
    controller text not null,
    config jsonb not null,
    autoplay boolean not null,
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
