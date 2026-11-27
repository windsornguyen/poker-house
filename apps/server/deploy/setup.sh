#!/usr/bin/env bash
set -euo pipefail

readonly COMMIT=$1
shift
readonly HOSTS=("$@")
readonly PG_MAJOR=19
readonly NODE_VERSION=v26.13.1
readonly UV_VERSION=0.12.1
readonly PNPM_VERSION=10.30.3
readonly REPO=https://github.com/windsornguyen/poker-house.git
readonly APP_USER=poker-house
readonly APP_DIR=/opt/poker-house
readonly ENV_FILE=/etc/poker-house/db.env

export DEBIAN_FRONTEND=noninteractive
export PATH="/opt/node/bin:$PATH"

apt-get update -qq
apt-get install -y -qq postgresql-common git curl xz-utils ca-certificates >/dev/null
/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y >/dev/null
apt-get install -y -qq "postgresql-$PG_MAJOR" >/dev/null

if [[ ! -f $ENV_FILE ]]; then
  install -d -m 700 "$(dirname "$ENV_FILE")"
  password=$(openssl rand -hex 24)
  printf 'DATABASE_URL=postgresql://poker_house:%s@localhost/poker_house\n' "$password" >"$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi
password=$(sed -n 's|^DATABASE_URL=postgresql://poker_house:\([^@]*\)@.*|\1|p' "$ENV_FILE")
cat >"/etc/postgresql/$PG_MAJOR/main/conf.d/poker-house.conf" <<CONF
shared_buffers = 512MB
effective_cache_size = 2GB
synchronous_commit = off
wal_compression = lz4
checkpoint_timeout = 15min
max_wal_size = 1GB
random_page_cost = 1.1
jit = off
max_connections = 20
CONF
systemctl restart "postgresql@$PG_MAJOR-main"
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<SQL
SELECT 'CREATE ROLE poker_house LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'poker_house')\gexec
ALTER ROLE poker_house PASSWORD '$password';
SELECT 'CREATE DATABASE poker_house OWNER poker_house' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'poker_house')\gexec
SQL

if [[ ! -x /usr/local/bin/uv ]]; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
if [[ ! -x /opt/node/bin/node ]]; then
  install -d /opt/node
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" | tar -xJ -C /opt/node --strip-components=1
fi
[[ -x /opt/node/bin/pnpm ]] || /opt/node/bin/npm install -g --silent "pnpm@$PNPM_VERSION"

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "/var/lib/$APP_USER" "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
as_app() {
  runuser -u "$APP_USER" -- env HOME="/var/lib/$APP_USER" PATH="/opt/node/bin:/usr/local/bin:/usr/bin:/bin" "$@"
}
[[ -d $APP_DIR/.git ]] || as_app git clone -q "$REPO" "$APP_DIR"
as_app git -C "$APP_DIR" fetch -q origin "$COMMIT"
as_app git -C "$APP_DIR" checkout -q --detach "$COMMIT"
cd "$APP_DIR"
as_app uv sync -q --frozen --package poker-house-server
as_app pnpm install --frozen-lockfile --silent
as_app pnpm build >/dev/null
psql "$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE")" -v ON_ERROR_STOP=1 -q -f "$APP_DIR/apps/server/schema.sql"

allow_hosts=()
for host in "${HOSTS[@]}"; do
  allow_hosts+=(--allow-host "$host")
done
cat >/etc/systemd/system/poker-house.service <<UNIT
[Unit]
Description=Poker House
After=network-online.target postgresql.service

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/python -m poker_house_server --host 0.0.0.0 --port 8787 ${allow_hosts[*]}
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q "postgresql@$PG_MAJOR-main.service" poker-house.service
systemctl restart poker-house.service

for _ in $(seq 1 30); do
  curl -fsS -o /dev/null http://127.0.0.1:8787/ && break
  sleep 1
done
curl -fsS -o /dev/null http://127.0.0.1:8787/
echo "Poker House $COMMIT is serving on port 8787 with Postgres $PG_MAJOR."
