#!/usr/bin/env bash
# Installs Doggybank on a Machine once, then deploys each release as one of two colors
# behind kamal-proxy. provision.ts runs it on the Machine as root.
#
#   $1        install, deploy, retire or rollback.
#   deploy:
#     $2      The commit being released. It names the release directory, so the same
#             commit cannot be unpacked twice.
#     $3      The release archive provision.ts uploaded. It is deleted once unpacked.
#     $4...   The host names requests reach the game server by. Others are refused.
#     SITE_URL  The site's address. Sign-in links point there, so a wrong one breaks
#               every email.
set -euo pipefail

readonly ACTION=$1
shift

# Pinned tools. kamal-proxy ships no release binaries, so the pinned Go builds it and
# checks the module against the public checksum database.
readonly PG_MAJOR=19
readonly NODE_VERSION=v26.13.1
readonly UV_VERSION=0.12.1
readonly PNPM_VERSION=10.30.3
readonly GO_VERSION=1.27.4
readonly GO_SHA256=7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840
readonly KAMAL_PROXY_VERSION=v0.10.3

# How long a deploy lets the old color finish its requests. Event streams never finish
# on their own, so they are cut here and the browser reconnects to the new color.
readonly DRAIN_TIMEOUT=10s

# Where the app, its releases, its settings and its secrets live.
readonly APP_USER=doggybank
readonly APP_DIR=/opt/doggybank
readonly RELEASES_DIR=$APP_DIR/releases
readonly ETC_DIR=/etc/doggybank
readonly ENV_FILE=$ETC_DIR/db.env
readonly AUTH_ENV_FILE=$ETC_DIR/auth.env
readonly GAME_ENV_FILE=$ETC_DIR/game.env
readonly SITE_ENV_FILE=$ETC_DIR/site.env
readonly HOSTS_ENV_FILE=$ETC_DIR/hosts.env
readonly LIVE_COLOR_FILE=$ETC_DIR/live.color
readonly PREVIOUS_COLOR_FILE=$ETC_DIR/previous.color
readonly AUTH_LISTEN_SCRIPT=$ETC_DIR/auth-listen.mjs

# Print the loopback port a color's game server listens on.
game_port() {
  case $1 in
    blue) echo 8801 ;;
    green) echo 8802 ;;
  esac
}

# Print the loopback port a color's sign-in service listens on.
auth_port() {
  case $1 in
    blue) echo 8811 ;;
    green) echo 8812 ;;
  esac
}

# Print the color that is not $1.
other_color() {
  case $1 in
    blue) echo green ;;
    green) echo blue ;;
  esac
}

# Run a command as the app user, with the tools install put on the path.
as_app() {
  runuser -u "$APP_USER" -- env HOME="/var/lib/$APP_USER" PATH="/opt/node/bin:/usr/local/bin:/usr/bin:/bin" "$@"
}

# Run a kamal-proxy command against one proxy: game on 8787 or auth on 8788.
kamal_proxy() {
  local proxy=$1
  shift
  KAMAL_PROXY_SOCKET=/run/kamal-proxy-$proxy/kamal-proxy.sock /usr/local/bin/kamal-proxy "$@"
}

# Move both proxies to a color. Each deploy returns once the color answers /readyz, new
# requests go to it, and the old color has drained.
switch_to() {
  local color=$1
  kamal_proxy game deploy game --target "127.0.0.1:$(game_port "$color")" \
    --health-check-path /readyz --drain-timeout "$DRAIN_TIMEOUT"
  kamal_proxy auth deploy auth --target "127.0.0.1:$(auth_port "$color")" \
    --health-check-path /readyz --drain-timeout "$DRAIN_TIMEOUT"
}

# Install Postgres, the tools, the secrets and the units on a new Machine.
install_machine() {
  # A second install would replace the secrets every session and signature depends on.
  if [[ -e $ETC_DIR ]]; then
    echo "already installed: $ETC_DIR exists" >&2
    exit 1
  fi

  # Postgres from its own repository, tuned for one small Machine.
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq postgresql-common curl xz-utils ca-certificates >/dev/null
  /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y >/dev/null
  apt-get install -y -qq "postgresql-$PG_MAJOR" >/dev/null
  cat >"/etc/postgresql/$PG_MAJOR/main/conf.d/doggybank.conf" <<'CONF'
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
  systemctl enable -q "postgresql@$PG_MAJOR-main.service"
  systemctl restart "postgresql@$PG_MAJOR-main.service"

  # The secrets, made once: the database password, the sign-in secret and mail key, and
  # the key the Worker signs each player with.
  install -d -m 755 "$ETC_DIR"
  local db_password
  db_password=$(openssl rand -hex 24)
  printf 'DATABASE_URL=postgresql://doggybank:%s@localhost/doggybank\n' "$db_password" >"$ENV_FILE"
  printf 'BETTER_AUTH_SECRET=%s\nMAIL_KEY=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" >"$AUTH_ENV_FILE"
  printf 'DOGGYBANK_PLAYER_KEY=%s\n' "$(openssl rand -hex 32)" >"$GAME_ENV_FILE"
  chmod 600 "$ENV_FILE" "$AUTH_ENV_FILE" "$GAME_ENV_FILE"

  # The database and the role that owns it.
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE doggybank LOGIN PASSWORD '$db_password';
CREATE DATABASE doggybank OWNER doggybank;
SQL

  # uv, Node and pnpm build and run releases. Go builds kamal-proxy.
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
  install -d /opt/node
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" | tar -xJ -C /opt/node --strip-components=1
  # npm starts with `#!/usr/bin/env node`, so node must be on the path.
  PATH="/opt/node/bin:$PATH" npm install -g --silent "pnpm@$PNPM_VERSION"
  local go_tmp
  go_tmp=$(mktemp -d)
  curl -fsSL "https://go.dev/dl/go$GO_VERSION.linux-amd64.tar.gz" -o "$go_tmp/go.tar.gz"
  printf '%s  %s/go.tar.gz\n' "$GO_SHA256" "$go_tmp" | sha256sum -c - >/dev/null
  tar -xzf "$go_tmp/go.tar.gz" -C /usr/local
  rm -rf "$go_tmp"
  env GOBIN=/usr/local/bin GOPATH=/var/cache/go HOME=/root /usr/local/go/bin/go install \
    "github.com/basecamp/kamal-proxy/cmd/kamal-proxy@$KAMAL_PROXY_VERSION"

  # The app user and where its releases go.
  useradd --system --create-home --home-dir "/var/lib/$APP_USER" "$APP_USER"
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR" "$RELEASES_DIR"

  # Each color's ports, and each proxy's public port.
  printf 'GAME_PORT=%s\nPORT=%s\n' "$(game_port blue)" "$(auth_port blue)" >"$ETC_DIR/blue.env"
  printf 'GAME_PORT=%s\nPORT=%s\n' "$(game_port green)" "$(auth_port green)" >"$ETC_DIR/green.env"
  echo 'HTTP_PORT=8787' >"$ETC_DIR/proxy-game.env"
  echo 'HTTP_PORT=8788' >"$ETC_DIR/proxy-auth.env"

  # Bind apps/auth/server.ts to its color's loopback port without changing apps/auth.
  cat >"$AUTH_LISTEN_SCRIPT" <<'MJS'
import net from 'node:net';

const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function (_port, _host, callback) {
  return listen.call(this, Number(process.env.PORT), '127.0.0.1', callback);
};
MJS

  # One game server and one sign-in service per color, each ready when it says so.
  cat >/etc/systemd/system/doggybank@.service <<UNIT
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
  cat >/etc/systemd/system/doggybank-auth@.service <<UNIT
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
EnvironmentFile=$SITE_ENV_FILE
EnvironmentFile=$ETC_DIR/%i.env
ExecStart=/opt/node/bin/node --import $AUTH_LISTEN_SCRIPT server.ts
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

  # One proxy per public port, so the Worker keeps its two origins. Each has its own socket
  # and saved state. kamal-proxy has no readiness protocol, so the unit is ready once this
  # run's log says the control socket is up. The journal keeps the line, so it is found even
  # when it came before the wait began.
  cat >/etc/systemd/system/kamal-proxy@.service <<UNIT
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
  systemctl daemon-reload
  systemctl enable --now -q kamal-proxy@game.service kamal-proxy@auth.service
  echo "Installed Postgres $PG_MAJOR and kamal-proxy $KAMAL_PROXY_VERSION on 8787 and 8788."
}

# Build a release, start it as the idle color and move traffic to it.
deploy_release() {
  local commit=$1
  local archive=$2
  shift 2
  : "${SITE_URL:?provision.ts passes SITE_URL}"

  # Deploys need what install made.
  if [[ ! -f $ENV_FILE || ! -x /usr/local/bin/kamal-proxy ]]; then
    echo "not installed: run provision.ts create first" >&2
    exit 1
  fi

  # The site address and the host names this release answers to.
  echo "BETTER_AUTH_URL=$SITE_URL" >"$SITE_ENV_FILE"
  local -a allow_hosts=()
  local host
  for host in "$@"; do
    allow_hosts+=(--allow-host "$host")
  done
  echo "ALLOW_HOSTS=${allow_hosts[*]}" >"$HOSTS_ENV_FILE"

  # Unpack and build the release in its own directory, beside the live one.
  local release_dir=$RELEASES_DIR/$commit
  if [[ -e $release_dir ]]; then
    echo "release $commit is already unpacked" >&2
    exit 1
  fi
  install -d -o "$APP_USER" -g "$APP_USER" "$release_dir"
  tar -xzf "$archive" -C "$release_dir"
  rm -f "$archive"
  chown -R "$APP_USER:$APP_USER" "$release_dir"
  (
    cd "$release_dir"
    as_app env UV_COMPILE_BYTECODE=1 uv sync -q --frozen --package doggybank-server
    as_app pnpm install --frozen-lockfile --silent
    as_app pnpm build >/dev/null
  )

  # Bring the database up to this release's schema and sign-in tables.
  local db_url
  db_url=$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE")
  psql "$db_url" -v ON_ERROR_STOP=1 -q -f "$release_dir/apps/server/schema.sql"
  # shellcheck source=/dev/null
  (set -a && source "$ENV_FILE" && source "$AUTH_ENV_FILE" && source "$SITE_ENV_FILE" && cd "$release_dir/apps/auth" && as_app /opt/node/bin/node migrate.ts)
  psql "$db_url" -v ON_ERROR_STOP=1 -q -f "$release_dir/apps/auth/players.sql"

  # The first release after install starts blue. Later ones take the color not serving.
  local live=""
  local idle=blue
  if [[ -f $LIVE_COLOR_FILE ]]; then
    live=$(cat "$LIVE_COLOR_FILE")
    idle=$(other_color "$live")
  fi

  # Start the release as the idle color, then move traffic to it.
  ln -sfn "$release_dir" "$ETC_DIR/$idle.release"
  systemctl enable -q "doggybank@$idle.service" "doggybank-auth@$idle.service"
  systemctl restart "doggybank@$idle.service" "doggybank-auth@$idle.service"
  switch_to "$idle"

  # The old color keeps running until retire, so a rollback is one switch away.
  if [[ -n $live ]]; then
    echo "$live" >"$PREVIOUS_COLOR_FILE"
    systemctl disable -q "doggybank@$live.service" "doggybank-auth@$live.service"
  fi
  echo "$idle" >"$LIVE_COLOR_FILE"
  echo "Doggybank $commit is live on $idle (ports $(game_port "$idle") and $(auth_port "$idle"))."
}

# Stop the color a deploy left running, and delete releases the live color does not use.
retire_color() {
  local live old
  live=$(cat "$LIVE_COLOR_FILE")
  if [[ ! -f $PREVIOUS_COLOR_FILE ]]; then
    echo "nothing to retire: $live is the only color" >&2
    exit 1
  fi
  old=$(cat "$PREVIOUS_COLOR_FILE")
  systemctl stop "doggybank@$old.service" "doggybank-auth@$old.service"
  rm -f "$PREVIOUS_COLOR_FILE"

  local keep dir
  keep=$(readlink -f "$ETC_DIR/$live.release")
  for dir in "$RELEASES_DIR"/*; do
    if [[ $(readlink -f "$dir") != "$keep" ]]; then
      rm -rf "$dir"
    fi
  done
  echo "Retired $old. $live is serving."
}

# Move traffic back to the color the last deploy replaced, and stop the new one.
roll_back() {
  if [[ ! -f $PREVIOUS_COLOR_FILE ]]; then
    echo "nothing to roll back to: no previous color" >&2
    exit 1
  fi
  local old bad
  old=$(cat "$PREVIOUS_COLOR_FILE")
  bad=$(cat "$LIVE_COLOR_FILE")
  systemctl enable -q "doggybank@$old.service" "doggybank-auth@$old.service"
  systemctl start "doggybank@$old.service" "doggybank-auth@$old.service"
  switch_to "$old"

  systemctl disable -q "doggybank@$bad.service" "doggybank-auth@$bad.service"
  systemctl stop "doggybank@$bad.service" "doggybank-auth@$bad.service"
  echo "$old" >"$LIVE_COLOR_FILE"
  rm -f "$PREVIOUS_COLOR_FILE"
  echo "Rolled back to $old."
}

case $ACTION in
  install) install_machine ;;
  deploy) deploy_release "$@" ;;
  retire) retire_color ;;
  rollback) roll_back ;;
  *)
    echo "unknown action: $ACTION (install, deploy, retire or rollback)" >&2
    exit 1
    ;;
esac
