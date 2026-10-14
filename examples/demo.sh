#!/usr/bin/env bash
# 虚构演示：起一个临时端口，用 wait-until 等到可连
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT=19876

python3 - <<PY &
import socket, time
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", $PORT))
s.listen(1)
time.sleep(0.5)
s.close()
PY

python3 "$ROOT/wait_until.py" port "$PORT" -t 5 -i 0.1
echo "demo ok"
