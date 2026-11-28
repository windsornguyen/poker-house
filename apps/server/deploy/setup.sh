#!/usr/bin/env bash
set -euo pipefail

readonly ACTION=${1:-deploy}
shift || true

readonly PG_MAJOR=19
readonly NODE_VERSION=v26.13.1
readonly UV_VERSION=0.12.1
readonly PNPM_VERSION=10.30.3
# kamal-proxy ships no release binaries, so it is built with a pinned Go, and Go checks
# the module against the public checksum database.
readonly GO_VERSION=1.27.4
readonly GO_SHA256=7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840
readonly KAMAL_PROXY_VERSION=v0.10.3
# How long a deploy lets the old color finish its requests. Event streams never finish
# on their own, so they are cut here and the browser reconnects to the new color.
readonly DRAIN_TIMEOUT=10s

readonly APP_USER=doggybank
readonly APP_DIR=/opt/doggybank
readonly RELEASES_DIR=$APP_DIR/releases
readonly ETC_DIR=/etc/doggybank
readonly ENV_FILE=$ETC_DIR/db.env
readonly AUTH_ENV_FILE=$ETC_DIR/auth.env
readonly GAME_ENV_FILE=$ETC_DIR/game.env
readonly HOSTS_ENV_FILE=$ETC_DIR/hosts.env
readonly LIVE_COLOR_FILE=$ETC_DIR/live.color
readonly PREVIOUS_COLOR_FILE=$ETC_DIR/previous.color
readonly AUTH_LISTEN_SCRIPT=$ETC_DIR/auth-listen.mjs

game_port() {
  case $1 in
    blue) echo 8801 ;;
    green) echo 8802 ;;
    *) exit 1 ;;
  esac
}

auth_port() {
  case $1 in
    blue) echo 8811 ;;
    green) echo 8812 ;;
    *) exit 1 ;;
  esac
}

other_color() {
  case $1 in
    blue) echo green ;;
    green) echo blue ;;
    *) echo blue ;;
  esac
}

write_if_changed() {
  local mode=$1
  local target=$2
  local tmp
  tmp=$(mktemp)
  cat >"$tmp"
  if [[ -f $target ]] && cmp -s "$tmp" "$target"; then
    rm -f "$tmp"
    return 1
  fi
  install -d -m 755 "$(dirname "$target")"
  install -m "$mode" "$tmp" "$target"
  rm -f "$tmp"
  return 0
}

# Runs a kamal-proxy command against one proxy: game on 8787 or auth on 8788.
kamal_proxy() {
  local proxy=$1
  shift
  KAMAL_PROXY_SOCKET=/run/kamal-proxy-$proxy/kamal-proxy.sock /usr/local/bin/kamal-proxy "$@"
}

# Moves both proxies to a color. Each deploy returns once the color answers /readyz,
# new requests go to it, and the old color has drained.
switch_to() {
  local color=$1
  kamal_proxy game deploy game --target "127.0.0.1:$(game_port "$color")" \
    --health-check-path /readyz --drain-timeout "$DRAIN_TIMEOUT"
  kamal_proxy auth deploy auth --target "127.0.0.1:$(auth_port "$color")" \
    --health-check-path /readyz --drain-timeout "$DRAIN_TIMEOUT"
}

if [[ $ACTION == retire ]]; then
  live=$(cat "$LIVE_COLOR_FILE")
  if [[ -f $PREVIOUS_COLOR_FILE ]]; then
    old=$(cat "$PREVIOUS_COLOR_FILE")
    if [[ -n $old && $old != "$live" ]]; then
      systemctl stop "doggybank@$old.service" "doggybank-auth@$old.service"
    fi
    rm -f "$PREVIOUS_COLOR_FILE"
  fi
  keep_blue=$(readlink -f "$ETC_DIR/blue.release" 2>/dev/null || true)
  keep_green=$(readlink -f "$ETC_DIR/green.release" 2>/dev/null || true)
  for dir in "$RELEASES_DIR"/*; do
    [[ -d $dir ]] || continue
    real=$(readlink -f "$dir")
    if [[ $real != "$keep_blue" && $real != "$keep_green" ]]; then
      rm -rf "$dir"
    fi
  done
  echo "Retired old color. $live is serving."
  exit 0
fi

if [[ $ACTION == rollback ]]; then
  if [[ ! -f $PREVIOUS_COLOR_FILE ]]; then
    echo "No previous color to roll back to." >&2
    exit 1
  fi
  old=$(cat "$PREVIOUS_COLOR_FILE")
  bad=$(cat "$LIVE_COLOR_FILE" 2>/dev/null || true)
  systemctl enable -q "doggybank@$old.service" "doggybank-auth@$old.service"
  systemctl start "doggybank@$old.service" "doggybank-auth@$old.service"
  switch_to "$old"
  printf '%s\n' "$old" >"$LIVE_COLOR_FILE"
  rm -f "$PREVIOUS_COLOR_FILE"
  if [[ -n $bad && $bad != "$old" ]]; then
    systemctl disable -q "doggybank@$bad.service" "doggybank-auth@$bad.service" || true
    systemctl stop "doggybank@$bad.service" "doggybank-auth@$bad.service"
  fi
  echo "Rolled back to $old."
  exit 0
fi

if [[ $ACTION != deploy ]]; then
  echo "Unknown action: $ACTION" >&2
  exit 1
fi

readonly COMMIT=$1
readonly ARCHIVE=$2
shift 2
readonly HOSTS=("$@")

export DEBIAN_FRONTEND=noninteractive
export PATH="/opt/node/bin:$PATH"

if ! dpkg -s "postgresql-$PG_MAJOR" curl xz-utils ca-certificates >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq postgresql-common curl xz-utils ca-certificates >/dev/null
  if ! dpkg -s "postgresql-$PG_MAJOR" >/dev/null 2>&1; then
    /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y >/dev/null
    apt-get install -y -qq "postgresql-$PG_MAJOR" >/dev/null
  fi
fi

install -d -m 755 "$ETC_DIR"
chmod 755 "$ETC_DIR"

if [[ ! -f $ENV_FILE ]]; then
  password=$(openssl rand -hex 24)
  printf 'DATABASE_URL=postgresql://doggybank:%s@localhost/doggybank\n' "$password" >"$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi
if [[ ! -f $AUTH_ENV_FILE ]]; then
  printf 'BETTER_AUTH_SECRET=%s\n' "$(openssl rand -hex 32)" >"$AUTH_ENV_FILE"
  chmod 600 "$AUTH_ENV_FILE"
fi
if [[ ! -f $GAME_ENV_FILE ]]; then
  printf 'DOGGYBANK_PLAYER_KEY=%s\n' "$(openssl rand -hex 32)" >"$GAME_ENV_FILE"
  chmod 600 "$GAME_ENV_FILE"
fi
grep -q '^MAIL_KEY=' "$AUTH_ENV_FILE" || printf 'MAIL_KEY=%s\n' "$(openssl rand -hex 32)" >>"$AUTH_ENV_FILE"
sed -i '/^BETTER_AUTH_URL=/d' "$AUTH_ENV_FILE"
printf 'BETTER_AUTH_URL=%s\n' "$SITE_URL" >>"$AUTH_ENV_FILE"
chmod 600 "$ENV_FILE" "$AUTH_ENV_FILE" "$GAME_ENV_FILE"

password=$(sed -n 's|^DATABASE_URL=postgresql://doggybank:\([^@]*\)@.*|\1|p' "$ENV_FILE")
if write_if_changed 644 "/etc/postgresql/$PG_MAJOR/main/conf.d/doggybank.conf" <<CONF; then
shared_buffers = 512MB
effective_cache_size = 1GB
synchronous_commit = off
wal_compression = lz4
checkpoint_timeout = 15min
max_wal_size = 1GB
random_page_cost = 1.1
jit = off
max_connections = 20
CONF
  systemctl restart "postgresql@$PG_MAJOR-main"
elif ! systemctl is-active --quiet "postgresql@$PG_MAJOR-main"; then
  systemctl start "postgresql@$PG_MAJOR-main"
fi

runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<SQL
SELECT 'CREATE ROLE doggybank LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'doggybank')\gexec
ALTER ROLE doggybank PASSWORD '$password';
SELECT 'CREATE DATABASE doggybank OWNER doggybank' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'doggybank')\gexec
SQL

if [[ ! -x /usr/local/bin/uv ]]; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
if [[ ! -x /opt/node/bin/node ]]; then
  install -d /opt/node
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" | tar -xJ -C /opt/node --strip-components=1
fi
[[ -x /opt/node/bin/pnpm ]] || /opt/node/bin/npm install -g --silent "pnpm@$PNPM_VERSION"

if [[ ! -x /usr/local/go/bin/go ]] || [[ $(/usr/local/go/bin/go env GOVERSION) != "go$GO_VERSION" ]]; then
  go_tmp=$(mktemp -d)
  curl -fsSL "https://go.dev/dl/go$GO_VERSION.linux-amd64.tar.gz" -o "$go_tmp/go.tar.gz"
  printf '%s  %s/go.tar.gz\n' "$GO_SHA256" "$go_tmp" | sha256sum -c - >/dev/null
  rm -rf /usr/local/go
  tar -xzf "$go_tmp/go.tar.gz" -C /usr/local
  rm -rf "$go_tmp"
fi
if [[ ! -x /usr/local/bin/kamal-proxy ]] || [[ $(/usr/local/go/bin/go version -m /usr/local/bin/kamal-proxy) != *"$KAMAL_PROXY_VERSION"* ]]; then
  env GOBIN=/usr/local/bin GOPATH=/var/cache/go HOME=/root /usr/local/go/bin/go install \
    "github.com/basecamp/kamal-proxy/cmd/kamal-proxy@$KAMAL_PROXY_VERSION"
fi

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "/var/lib/$APP_USER" "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR" "$RELEASES_DIR"
as_app() {
  runuser -u "$APP_USER" -- env HOME="/var/lib/$APP_USER" PATH="/opt/node/bin:/usr/local/bin:/usr/bin:/bin" "$@"
}

release_dir=$RELEASES_DIR/$COMMIT
if [[ ! -f $release_dir/.ready ]]; then
  rm -rf "$release_dir"
  install -d -o "$APP_USER" -g "$APP_USER" "$release_dir"
  tar -xzf "$ARCHIVE" -C "$release_dir"
  chown -R "$APP_USER:$APP_USER" "$release_dir"
  (
    cd "$release_dir"
    as_app env UV_COMPILE_BYTECODE=1 uv sync -q --frozen --package doggybank-server
    as_app pnpm install --frozen-lockfile --silent
    as_app pnpm build >/dev/null
  )
  touch "$release_dir/.ready"
fi
rm -f "$ARCHIVE"

db_url=$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE")
psql "$db_url" -v ON_ERROR_STOP=1 -q -f "$release_dir/apps/server/schema.sql"
# shellcheck source=/dev/null
(set -a && source "$ENV_FILE" && source "$AUTH_ENV_FILE" && cd "$release_dir/apps/auth" && as_app node migrate.ts)
psql "$db_url" -v ON_ERROR_STOP=1 -q -f "$release_dir/apps/auth/players.sql"

write_if_changed 644 "$ETC_DIR/blue.env" <<'ENV' || true
GAME_PORT=8801
PORT=8811
ENV
write_if_changed 644 "$ETC_DIR/green.env" <<'ENV' || true
GAME_PORT=8802
PORT=8812
ENV

allow_hosts=()
for host in "${HOSTS[@]}"; do
  allow_hosts+=(--allow-host "$host")
done
write_if_changed 644 "$HOSTS_ENV_FILE" <<ENV || true
ALLOW_HOSTS=${allow_hosts[*]}
ENV

# Binds apps/auth/server.ts to 127.0.0.1:$PORT without altering apps/auth.
write_if_changed 644 "$AUTH_LISTEN_SCRIPT" <<'MJS' || true
import net from 'node:net';

const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function (_port, _host, callback) {
  return listen.call(this, Number(process.env.PORT), '127.0.0.1', callback);
};
MJS

units_changed=0
write_if_changed 644 /etc/systemd/system/doggybank@.service <<UNIT && units_changed=1 || true
[Unit]
Description=Doggybank (%i)
Requires=postgresql@$PG_MAJOR-main.service
After=network-online.target postgresql@$PG_MAJOR-main.service

[Service]
Type=notify
NotifyAccess=all
User=$APP_USER
WorkingDirectory=$ETC_DIR/%i.release
EnvironmentFile=$ENV_FILE
EnvironmentFile=$GAME_ENV_FILE
EnvironmentFile=$ETC_DIR/%i.env
EnvironmentFile=$HOSTS_ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$ETC_DIR/%i.release/.venv/bin/python -m doggybank_server --host 127.0.0.1 --port \$GAME_PORT \$ALLOW_HOSTS
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

write_if_changed 644 /etc/systemd/system/doggybank-auth@.service <<UNIT && units_changed=1 || true
[Unit]
Description=Doggybank sign-in (%i)
Requires=postgresql@$PG_MAJOR-main.service
After=network-online.target postgresql@$PG_MAJOR-main.service

[Service]
Type=notify
NotifyAccess=all
User=$APP_USER
WorkingDirectory=$ETC_DIR/%i.release/apps/auth
EnvironmentFile=$ENV_FILE
EnvironmentFile=$AUTH_ENV_FILE
EnvironmentFile=$ETC_DIR/%i.env
ExecStart=/opt/node/bin/node --import $AUTH_LISTEN_SCRIPT server.ts
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

write_if_changed 644 "$ETC_DIR/proxy-game.env" <<'ENV' || true
HTTP_PORT=8787
ENV
write_if_changed 644 "$ETC_DIR/proxy-auth.env" <<'ENV' || true
HTTP_PORT=8788
ENV

# One proxy per public port, so the Worker keeps its two origins. Each instance has its
# own socket and saved state. kamal-proxy has no readiness protocol, so the unit is ready
# once this run's log says the control socket is up. The journal keeps the line, so it is
# found even when it came before the wait began.
write_if_changed 644 /etc/systemd/system/kamal-proxy@.service <<UNIT && units_changed=1 || true
[Unit]
Description=kamal-proxy (%i)
After=network-online.target

[Service]
User=$APP_USER
RuntimeDirectory=kamal-proxy-%i
StateDirectory=kamal-proxy-%i
Environment=KAMAL_PROXY_SOCKET=/run/kamal-proxy-%i/kamal-proxy.sock HOME=/var/lib/kamal-proxy-%i
EnvironmentFile=$ETC_DIR/proxy-%i.env
ExecStart=/usr/local/bin/kamal-proxy run --http-port \$HTTP_PORT --https-port 0
ExecStartPost=+/usr/bin/timeout 10 /bin/bash -c 'grep -m1 -q "Server started" < <(journalctl -f -n all -o cat _SYSTEMD_INVOCATION_ID=\$\$INVOCATION_ID)'
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

(( units_changed )) && systemctl daemon-reload

live=$(cat "$LIVE_COLOR_FILE" 2>/dev/null || true)
idle=$(other_color "$live")
ln -sfn "$release_dir" "$ETC_DIR/$idle.release"

systemctl enable -q "postgresql@$PG_MAJOR-main.service" "doggybank@$idle.service" "doggybank-auth@$idle.service"
systemctl restart "doggybank@$idle.service" "doggybank-auth@$idle.service"

# The first deploy behind the proxies frees ports 8787 and 8788 from the single-copy units.
for legacy in doggybank.service doggybank-auth.service; do
  if systemctl is-active --quiet "$legacy"; then
    systemctl disable --now -q "$legacy"
  fi
done
systemctl enable --now -q kamal-proxy@game.service kamal-proxy@auth.service
switch_to "$idle"

if [[ -n $live && $live != "$idle" ]]; then
  printf '%s\n' "$live" >"$PREVIOUS_COLOR_FILE"
  systemctl disable -q "doggybank@$live.service" "doggybank-auth@$live.service" || true
fi
printf '%s\n' "$idle" >"$LIVE_COLOR_FILE"
echo "Doggybank $COMMIT is live on $idle (ports $(game_port "$idle") and $(auth_port "$idle") behind kamal-proxy on 8787 and 8788), with Postgres $PG_MAJOR."
