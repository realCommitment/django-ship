#!/usr/bin/env bash
# Prepare this checkout (the primary one or an Orca worktree): its own ports, its own Compose project
# (named after the directory), dependencies and migrations. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

set_env() {
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}

# Picked once per checkout, so two checkouts never share a database or a port. The marker holds the
# checkout path because Orca copies the primary checkout's .env into new worktrees.
if ! grep -qx "WORKTREE_PORTS=$PWD" .env; then
  # Docker publishes ports without a listening socket, so a bind test alone can hand out a port a running
  # container already holds; exclude those explicitly.
  # shortcut: ports of stopped Compose stacks are not excluded; rerun with a fresh .env if a start collides.
  read -r pg redis django vite < <(python3 - "$(docker ps --format '{{.Ports}}')" <<'PY'
import re, socket, sys
taken = {int(p) for p in re.findall(r":(\d+)->", sys.argv[1])}
socks, ports = [], []
while len(ports) < 4:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    socks.append(s)  # held open so the four ports differ
    if s.getsockname()[1] not in taken:
        ports.append(s.getsockname()[1])
print(*ports)
PY
)
  set_env POSTGRES_PORT "$pg"
  set_env REDIS_PORT "$redis"
  set_env DJANGO_PORT "$django"
  set_env DJANGO_VITE_PORT "$vite"
  set_env DATABASE_URL "\"postgresql://postgres:postgres@127.0.0.1:$pg/project\""
  set_env REDIS_URL "\"redis://127.0.0.1:$redis\""
  set_env WORKTREE_PORTS "$PWD"
fi

# mise exported the .env as it was before (a copy of the primary's), and both Compose and django-environ
# prefer the environment over the file, so reload it.
set -a
source .env
set +a

docker compose up -d --wait
uv sync --frozen
npm ci
uv run manage.py migrate --noinput
uv run manage.py sync_sites
