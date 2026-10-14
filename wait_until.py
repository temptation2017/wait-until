#!/usr/bin/env python3
"""wait-until: block until a URL, port, file, log line, or command is ready.

Stdlib only. Exit 0 on success, 1 on timeout/failure, 2 on bad args.
Useful for local agents, scripts, and CI before the next step runs.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional
from urllib.parse import urlparse


VERSION = "1.0.0"
DEFAULT_TIMEOUT = 60.0
DEFAULT_INTERVAL = 1.0


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def now_mono() -> float:
    return time.monotonic()


def parse_host_port(target: str, default_port: Optional[int] = None) -> tuple[str, int]:
    """Accept host:port, :port, or bare port."""
    s = target.strip()
    if s.isdigit():
        if default_port is not None:
            raise ValueError("ambiguous: bare number with default host")
        return "127.0.0.1", int(s)
    if s.startswith(":"):
        return "127.0.0.1", int(s[1:])
    if "://" in s:
        u = urlparse(s)
        host = u.hostname or "127.0.0.1"
        port = u.port
        if port is None:
            port = 443 if u.scheme == "https" else 80
        return host, port
    if ":" in s:
        host, _, port_s = s.rpartition(":")
        host = host or "127.0.0.1"
        return host, int(port_s)
    raise ValueError(f"need host:port or port, got {target!r}")


def check_port(host: str, port: int, connect_timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=connect_timeout):
            return True
    except OSError:
        return False


def check_url(
    url: str,
    method: str = "GET",
    expect_status: Optional[int] = None,
    connect_timeout: float = 2.0,
) -> bool:
    req = urllib.request.Request(url, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=connect_timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            if expect_status is not None:
                return int(code) == expect_status
            return 200 <= int(code) < 400
    except urllib.error.HTTPError as exc:
        if expect_status is not None:
            return int(exc.code) == expect_status
        return False
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def check_file(path: str, non_empty: bool = False) -> bool:
    if not os.path.isfile(path):
        return False
    if non_empty and os.path.getsize(path) == 0:
        return False
    return True


def check_log_contains(path: str, needle: str, from_start: bool = False) -> Callable[[], bool]:
    """Return a checker that only reads new bytes after first call (unless from_start)."""
    state = {"pos": 0 if from_start else None, "buf": ""}

    def _check() -> bool:
        if not os.path.isfile(path):
            return False
        try:
            size = os.path.getsize(path)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if state["pos"] is None:
                    # first poll: start at EOF so we only see new lines
                    state["pos"] = size
                    return False
                if size < state["pos"]:
                    # truncated / rotated
                    state["pos"] = 0
                    state["buf"] = ""
                f.seek(state["pos"])
                chunk = f.read()
                state["pos"] = f.tell()
        except OSError:
            return False
        state["buf"] += chunk
        # keep a rolling window so huge logs don't grow forever
        if len(state["buf"]) > 1_000_000:
            state["buf"] = state["buf"][-500_000:]
        if needle in state["buf"]:
            return True
        # drop fully scanned complete lines except last partial
        if "\n" in state["buf"]:
            parts = state["buf"].rsplit("\n", 1)
            state["buf"] = parts[-1]
        return False

    return _check


def check_cmd(argv: list[str], shell: bool = False) -> bool:
    try:
        r = subprocess.run(
            argv if not shell else " ".join(argv),
            shell=shell,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def wait_loop(
    checker: Callable[[], bool],
    timeout: float,
    interval: float,
    label: str,
    quiet: bool,
) -> int:
    deadline = now_mono() + timeout
    attempt = 0
    while True:
        attempt += 1
        ok = False
        try:
            ok = checker()
        except Exception as exc:  # noqa: BLE001 — surface and keep polling
            if not quiet:
                eprint(f"[wait-until] check error: {exc}")
        if ok:
            if not quiet:
                eprint(f"[wait-until] ready: {label} (attempt {attempt})")
            return 0
        left = deadline - now_mono()
        if left <= 0:
            if not quiet:
                eprint(f"[wait-until] timeout after {timeout:g}s: {label}")
            return 1
        time.sleep(min(interval, max(left, 0.05)))


def common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"最长等待秒数（默认 {DEFAULT_TIMEOUT:g}）",
    )
    sp.add_argument(
        "-i",
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help=f"轮询间隔秒数（默认 {DEFAULT_INTERVAL:g}）",
    )
    sp.add_argument("-q", "--quiet", action="store_true", help="少说话，只靠退出码")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wait-until",
        description="等到 URL / 端口 / 文件 / 日志行 / 命令成功后再退出（适合 Agent 与 CI）。",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    sub = p.add_subparsers(dest="cmd", required=True)

    p_url = sub.add_parser("url", help="等到 HTTP(S) 返回成功状态")
    common_flags(p_url)
    p_url.add_argument("url", help="例如 http://127.0.0.1:3000/health")
    p_url.add_argument(
        "--method",
        default="GET",
        help="HTTP 方法（默认 GET）",
    )
    p_url.add_argument(
        "--status",
        type=int,
        default=None,
        help="期望的精确状态码（默认接受 2xx/3xx）",
    )

    p_port = sub.add_parser("port", help="等到 TCP 端口可连接")
    common_flags(p_port)
    p_port.add_argument(
        "target",
        help="端口、host:port 或 :port（默认主机 127.0.0.1）",
    )

    p_file = sub.add_parser("file", help="等到文件出现")
    common_flags(p_file)
    p_file.add_argument("path", help="文件路径")
    p_file.add_argument(
        "--non-empty",
        action="store_true",
        help="还要求文件大小 > 0",
    )

    p_log = sub.add_parser("log", help="等到日志文件里出现某段文字")
    common_flags(p_log)
    p_log.add_argument("path", help="日志文件路径")
    p_log.add_argument("text", help="要匹配的子串（字面量，非正则）")
    p_log.add_argument(
        "--from-start",
        action="store_true",
        help="从文件开头扫（默认只看启动后的新内容）",
    )

    p_run = sub.add_parser("cmd", help="等到外部命令退出码为 0")
    common_flags(p_run)
    p_run.add_argument(
        "argv",
        nargs=argparse.REMAINDER,
        help="命令及参数；建议写成: wait-until cmd -- echo ok",
    )

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        eprint("timeout must be > 0")
        return 2
    if args.interval <= 0:
        eprint("interval must be > 0")
        return 2

    quiet = args.quiet
    timeout = args.timeout
    interval = args.interval

    if args.cmd == "url":
        label = f"url {args.url}"
        checker = lambda: check_url(args.url, method=args.method, expect_status=args.status)
    elif args.cmd == "port":
        try:
            host, port = parse_host_port(args.target)
        except ValueError as exc:
            eprint(exc)
            return 2
        label = f"port {host}:{port}"
        checker = lambda h=host, p=port: check_port(h, p)
    elif args.cmd == "file":
        label = f"file {args.path}"
        checker = lambda: check_file(args.path, non_empty=args.non_empty)
    elif args.cmd == "log":
        label = f"log {args.path!r} contains {args.text!r}"
        checker = check_log_contains(args.path, args.text, from_start=args.from_start)
    elif args.cmd == "cmd":
        argv_rest = list(args.argv)
        if argv_rest and argv_rest[0] == "--":
            argv_rest = argv_rest[1:]
        if not argv_rest:
            eprint("cmd: pass a command after -- , e.g. wait-until cmd -- true")
            return 2
        label = "cmd " + " ".join(argv_rest)
        checker = lambda: check_cmd(argv_rest)
    else:
        parser.print_help()
        return 2

    if not quiet:
        eprint(f"[wait-until] waiting up to {timeout:g}s (every {interval:g}s): {label}")
    return wait_loop(checker, timeout, interval, label, quiet)


if __name__ == "__main__":
    sys.exit(main())
