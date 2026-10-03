from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import importlib.util
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs

from .config import Config, CONTROLLERS
from .scenarios import SCENARIOS
from .engine import simulate
from .cli import write_json

ROOT = Path(__file__).resolve().parent.parent
CAPACITY = threading.BoundedSemaphore(2)


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200, content_type="application/json"):
        data = json.dumps(value, allow_nan=False).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        uri = urlparse(self.path)
        if uri.path in ("/", "/app.js", "/style.css"):
            filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[uri.path]
            content_type = {"/": "text/html", "/app.js": "text/javascript", "/style.css": "text/css"}[uri.path]
            return self.send((Path(__file__).parent / "web" / filename).read_bytes(), content_type=content_type)
        if uri.path == "/api/catalog":
            return self.send({"scenarios": {k: asdict(v) for k, v in SCENARIOS.items()},
                              "controllers": [c for c in CONTROLLERS if c not in ("imitation","mappo") or (importlib.util.find_spec("torch") is not None and (ROOT / "models" / (c+".json")).exists())], "defaults": asdict(Config())})
        if uri.path == "/api/campaigns":
            return self.send(sorted(p.parent.name for p in (ROOT / "artifacts").glob("*/summary.json")))
        if uri.path == "/api/summary":
            name = parse_qs(uri.query).get("campaign", ["full-campaign"])[0]
            if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):
                return self.send({"error": "Invalid campaign identifier"}, 400)
            path = ROOT / "artifacts" / name / "summary.json"
            if path.exists():
                return self.send(json.loads(path.read_text()))
            return self.send({"error": "Campaign has not completed; use the CLI to run the matrix."}, 404)
        self.send({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path != "/api/run":
            return self.send({"error": "Not found"}, 404)
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in (f"http://{host}", f"https://{host}"):
            return self.send({"error": "Only same-origin requests are accepted"}, 403)
        if not host.startswith(("127.0.0.1:", "localhost:")):
            return self.send({"error": "Loopback host required"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 10000:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            allowed = {"scenario", "controller", "drones", "cooperative_fraction", "fixed_wing_fraction", "seed", "duration", "dt", "admission", "admission_limit", "routes", "require_invariant_backup"}
            if set(data) - allowed:
                raise ValueError("Unsupported configuration fields")
            for name in ("drones", "seed", "admission_limit"):
                if name in data and (not isinstance(data[name], int) or isinstance(data[name], bool)):
                    raise ValueError(f"{name} must be an integer")
            cfg = Config(**data).validate()
            if cfg.controller in ('imitation','mappo'):
                from .learning import checkpoint_digest,load_model
                checkpoint=ROOT / 'models' / (cfg.controller + '.json')
                load_model(checkpoint,stage=cfg.controller)
                cfg=Config(**{**asdict(cfg),'checkpoint':str(checkpoint),'checkpoint_sha256':checkpoint_digest(checkpoint)})
            if cfg.controller == "evolved":
                from .policy import load_policy
                weights, _ = load_policy(ROOT / "profiles" / "predictive-preferences.json")
                cfg = Config(**{**asdict(cfg), **weights}).validate()
        except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
            return self.send({"error": str(exc)}, 400)
        if not CAPACITY.acquire(blocking=False):
            return self.send({"error": "Two simulations are already running; retry shortly"}, 429)
        try:
            result = simulate(cfg, record=True)
            write_json(ROOT / "artifacts" / "replays" / f"{result['run_id']}.json", result)
            self.send(result)
        except ValueError as exc:
            self.send({"error": str(exc)}, 400)
        finally:
            CAPACITY.release()


def serve(port=8765):
    print(f"Simulation lab: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
