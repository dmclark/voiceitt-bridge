#!/usr/bin/env python3
"""Tiny HTTP server for the Voiceitt scratchpad.

Replaces `python3 -m http.server`. Two responsibilities:

  1. Serve `bridge/dictate.html` (and any sibling assets) as plain
     static content, exactly like `http.server` did.
  2. Accept `POST /transform` with a JSON body `{"text": "..."}`,
     shell out to the `voiceitt-transform` CLI, and return the
     cleaned text as `text/plain`.

Why a custom server instead of `python3 -m http.server`?
The page's auto-trigger (ERD §1.3) needs to round-trip dictated text
through an LLM. Doing the LLM call in the browser would force the API
key into localStorage; doing it through a local endpoint that shells
out to `voiceitt-transform` keeps the key in the shell env where it
already lives (Raycast inherits the user's shell env on launch — see
ROADMAP §1 open question #3).

This is the v0 of ERD §1.4 / §1.6: one endpoint, no prompt picker
plumbing yet, no rolling-context buffer. The existing Gemini-backed
`voiceitt-transform` (v0 of ERD §1.5) is invoked verbatim.

Configuration via env vars (all optional):
  VOICEITT_BRIDGE_PORT          default 7531
  VOICEITT_BRIDGE_DIR           default ~/.config/voiceitt-bridge
  VOICEITT_TRANSFORM_CMD        default $VOICEITT_BRIDGE_DIR/voiceitt-transform
  VOICEITT_TRANSFORM_HARD_TIMEOUT  default 10  (seconds; outer cap on
                                                the subprocess; the CLI
                                                has its own curl --max-time)
"""

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue


PORT = int(os.environ.get("VOICEITT_BRIDGE_PORT", "7531"))
SERVE_DIR = os.environ.get(
    "VOICEITT_BRIDGE_DIR",
    os.path.expanduser("~/.config/voiceitt-bridge"),
)
TRANSFORM_CMD = os.environ.get(
    "VOICEITT_TRANSFORM_CMD",
    os.path.join(SERVE_DIR, "voiceitt-transform"),
)
HARD_TIMEOUT = float(os.environ.get("VOICEITT_TRANSFORM_HARD_TIMEOUT", "10"))

# Local-file loader (PARKING-LOT 2026-05-13 → graduated).
# Hard caps the user agreed on:
#   - 50 KB max
#   - UTF-8 only
#   - Path must resolve under $HOME so a stray POST can't slurp /etc/...
# Single in-memory slot — no history / no multi-file (parking lot).
MAX_LOAD_BYTES = 50 * 1024
LOAD_HOME = os.path.realpath(os.path.expanduser("~"))

_state_lock = threading.Lock()
_loaded = {"path": "", "text": ""}
_subscribers: "list[Queue]" = []


def _broadcast_reload():
    """Wake every connected SSE subscriber so the open scratchpad tab
    re-fetches /file. Best-effort — a full queue means the client is
    already behind, drop the extra event silently."""
    with _state_lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put_nowait("reload")
        except Exception:
            pass


def _snip(s, n=120):
    """Truncate text for log lines so server.log stays grep-able."""
    s = s or ""
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _ts():
    """Local timestamp prefix for log lines (ISO-ish, second precision)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    # Trim the default per-request access log to one line on stderr.
    def log_message(self, fmt, *args):
        sys.stderr.write(
            "%s %s - %s\n" % (_ts(), self.address_string(), fmt % args)
        )

    # Suppress the stock per-request access line and send_error's
    # "code N, message ..." follow-up. We already emit a richer
    # "transform: in=… out=…" line on success and a multi-line block
    # with the upstream API body on failure; the default lines are
    # pure noise on top of that.
    def log_request(self, *args, **kwargs):
        pass

    def log_error(self, *args, **kwargs):
        pass

    def do_GET(self):
        # Local-file loader endpoints (see MAX_LOAD_BYTES note above).
        # Routed before SimpleHTTPRequestHandler.do_GET so they don't
        # collide with on-disk paths under SERVE_DIR.
        if self.path == "/file":
            with _state_lock:
                body = json.dumps(_loaded).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/events":
            self._serve_events()
            return
        return super().do_GET()

    def _serve_events(self):
        """Long-lived Server-Sent Events stream. Emits `reload` whenever a
        new file is POSTed to /load, plus a 15 s heartbeat comment so any
        proxy/idle timeout doesn't silently drop the connection."""
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "keep-alive")
        self.end_headers()

        q: Queue = Queue()
        with _state_lock:
            _subscribers.append(q)
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    evt = q.get(timeout=15)
                    self.wfile.write(("event: %s\ndata: 1\n\n" % evt).encode("utf-8"))
                    self.wfile.flush()
                except Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _state_lock:
                try:
                    _subscribers.remove(q)
                except ValueError:
                    pass

    def do_POST(self):
        if self.path == "/load":
            self._handle_load()
            return
        if self.path != "/transform":
            self.send_error(404, "unknown endpoint")
            return

        length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "invalid JSON body")
            return

        text = payload.get("text", "")
        if not isinstance(text, str):
            self.send_error(400, "'text' must be a string")
            return
        if not text:
            # Pass-through: nothing to transform, return empty 200.
            self._send_text(200, "")
            return

        try:
            result = subprocess.run(
                [TRANSFORM_CMD],
                input=text,
                capture_output=True,
                text=True,
                timeout=HARD_TIMEOUT,
                check=False,
            )
        except FileNotFoundError:
            self.send_error(
                500,
                f"voiceitt-transform not found at {TRANSFORM_CMD}",
            )
            return
        except subprocess.TimeoutExpired:
            self.send_error(504, f"voiceitt-transform timed out after {HARD_TIMEOUT}s")
            return

        if result.returncode != 0:
            # Surface stderr in the server log; the page treats any non-2xx
            # as "fail open with raw text" so the user is never blocked.
            sys.stderr.write(
                "%s voiceitt-transform exit %d on input %r:\n%s\n"
                % (_ts(), result.returncode, _snip(text), (result.stderr or "").rstrip())
            )
            self.send_error(
                502,
                (result.stderr or "voiceitt-transform failed").splitlines()[-1][:200],
            )
            return

        # Debug visibility — log each round-trip's input/output snippet to
        # server.log so behaviour is inspectable without DevTools.
        sys.stderr.write(
            "%s transform: in=%r out=%r%s\n"
            % (_ts(), _snip(text), _snip(result.stdout),
               " (unchanged)" if result.stdout == text else "")
        )
        self._send_text(200, result.stdout)

    def _handle_load(self):
        """POST /load — body `{"path": "<absolute or ~-relative path>"}`.
        Reads the file into the in-memory slot and notifies SSE subscribers
        so the open scratchpad tab swaps content live. Constraints:
          - path must resolve under $HOME (no /etc, no other users)
          - file ≤ MAX_LOAD_BYTES (50 KB)
          - must decode as UTF-8 (no binary)
        Returns 200 "ok" on success; 4xx with a one-line reason otherwise."""
        length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "invalid JSON body")
            return

        path = payload.get("path", "")
        if not isinstance(path, str) or not path:
            self.send_error(400, "'path' must be a non-empty string")
            return

        abspath = os.path.realpath(os.path.expanduser(path))
        if abspath != LOAD_HOME and not abspath.startswith(LOAD_HOME + os.sep):
            self.send_error(403, "path resolves outside $HOME")
            return
        if not os.path.isfile(abspath):
            self.send_error(404, "not a regular file")
            return
        try:
            size = os.path.getsize(abspath)
        except OSError as e:
            self.send_error(500, "stat failed: %s" % e)
            return
        if size > MAX_LOAD_BYTES:
            self.send_error(
                413,
                "file too large (%d bytes > %d limit)" % (size, MAX_LOAD_BYTES),
            )
            return
        try:
            with open(abspath, "rb") as f:
                blob = f.read()
        except OSError as e:
            self.send_error(500, "read failed: %s" % e)
            return
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            self.send_error(415, "file is not valid UTF-8")
            return

        with _state_lock:
            _loaded["path"] = abspath
            _loaded["text"] = text
        sys.stderr.write(
            "%s loaded %s (%d bytes, %d chars)\n"
            % (_ts(), abspath, size, len(text))
        )
        _broadcast_reload()
        self._send_text(200, "ok")

    def _send_text(self, status, body):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stderr.write(
        "%s voiceitt-bridge: serving %s on http://127.0.0.1:%d\n"
        "%s voiceitt-bridge: transform CLI = %s\n"
        % (_ts(), SERVE_DIR, PORT, _ts(), TRANSFORM_CMD)
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
