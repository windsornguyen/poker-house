-- An account exists only for a listed player, and goes with the player.
do $$
begin
  if not exists (select from pg_constraint where conname = 'user_email_player') then
    alter table auth."user" add constraint user_email_player
      foreign key (email) references poker.player (email) on delete cascade;
  end if;
end $$;
