import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .core import Store
from .collector import Collector

WEB = Path(__file__).resolve().parent.parent / "web"


def data_directory():
    if os.environ.get("HIRESAY_DATA_DIR"):
        return Path(os.environ["HIRESAY_DATA_DIR"]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "HireSay"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "hiresay"


def handler_for(store, collector, port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {"http://" + h for h in hosts}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, body, mime="application/json; charset=utf-8"):
            data = json.dumps(body).encode() if mime.startswith("application/json") else body
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(data)

        def trusted(self, mutation=False):
            if self.headers.get("Host") not in hosts:
                self.respond(403, {"error": "Invalid local host"})
                return False
            if mutation and (self.headers.get("Origin") not in origins or self.headers.get("X-HireSay") != "local" or not self.headers.get("Content-Type", "").startswith("application/json")):
                self.respond(403, {"error": "Use the HireSay dashboard on this computer"})
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            path = urlsplit(self.path).path
            if path == "/api/state":
                with store.db() as db:
                    n = db.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
                return self.respond(200, {"settings": store.settings(), "collector": collector.status(), "posts": store.posts(), "scans": store.scans(), "connections_count": n})
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "application/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}
            if path in files:
                name, mime = files[path]
                return self.respond(200, (WEB / name).read_bytes(), mime)
            self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if not self.trusted(mutation=True):
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 5_000_000:
                    raise ValueError("Request must be under 5 MB")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected an object")
                path = urlsplit(self.path).path
                if path == "/api/scan":
                    hours = data.get("hours", store.settings()["lookback_hours"])
                    if type(hours) != int or not 1 <= hours <= 720:
                        raise ValueError("Lookback must be 1–720 hours")
                    collector.start("scan", hours)
                elif path == "/api/login":
                    collector.start("login")
                elif path == "/api/cancel":
                    collector.cancel.set()
                elif path == "/api/settings":
                    store.save_settings(data)
                elif path == "/api/status":
                    store.set_status(str(data.get("id", "")), data.get("status"))
                elif path == "/api/connections":
                    if not isinstance(data.get("csv"), str):
                        raise ValueError("CSV text required")
                    return self.respond(200, {"count": store.import_connections(data["csv"])})
                else:
                    return self.respond(404, {"error": "Not found"})
                self.respond(200, {"ok": True})
            except (ValueError, TypeError, KeyError) as e:
                self.respond(400, {"error": str(e)[:300]})
            except Exception:
                self.respond(500, {"error": "Local operation failed. Restart HireSay and try again."})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="HireSay local dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a port from 1024 to 65535")
    store = Store(data_directory())
    collector = Collector(store)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(store, collector, args.port))
    except OSError:
        print("HireSay couldn't use this port. If it's already running, open http://127.0.0.1:8765; otherwise try --port 8766.")
        return 1
    server.daemon_threads = True
    stop = threading.Event()
    threading.Thread(target=collector.scheduler, args=(stop,), daemon=True).start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"\nHireSay is ready at {url}\nKeep this window open for daily scans. Press Control-C to stop.\nData: {store.root}\n")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping HireSay…")
    finally:
        collector.cancel.set()
        stop.set()
        server.server_close()
    return 0
