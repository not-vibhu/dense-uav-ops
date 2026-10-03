"""Loopback-only research UI, one campaign at a time, no shell execution."""
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit
import uuid

from .profile import Profile


def request_config(body, output):
    if not isinstance(body, dict) or set(body) != {'profile', 'rates', 'limits', 'seeds', 'scenarios'}:
        raise ValueError('Expected profile, rates, limits, seeds and scenarios')
    p = Profile(**body['profile']).validate()
    if not isinstance(body['scenarios'], list) or not 1 <= len(body['scenarios']) <= 6 or len(set(body['scenarios'])) != len(body['scenarios']):
        raise ValueError('Choose one to six distinct scenarios')
    profiles = [replace(p, scenario=s).validate() for s in body['scenarios']]
    for key in ('rates', 'limits', 'seeds'):
        values = body[key]
        if not isinstance(values, list) or not values or len(values) != len(set(values)) or len(values) > 300:
            raise ValueError('Invalid or duplicate grid entries')
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
            raise ValueError('Finite numeric grid entries required')
    if any(x <= 0 for x in body['rates']) or any(not isinstance(x, int) or not 1 <= x <= 500 for x in body['limits']) or any(not isinstance(x, int) or x < 0 for x in body['seeds']):
        raise ValueError('Invalid demand rates, integer limits or seeds')
    total = len(profiles)*len(body['rates'])*len(body['limits'])*len(body['seeds'])
    if total > 600 or p.warmup_s+p.measurement_s+p.drain_s > 1800:
        raise ValueError('Lab budget exceeded; use the CLI for larger campaigns')
    from .simulation import build_traffic
    for profile in profiles:
        for rate in body['rates']:
            build_traffic(profile, rate, body['seeds'][0])
    return SimpleNamespace(rates=body['rates'], occupancy_limits=body['limits'],
                           seeds=body['seeds'], out=output), profiles, total


def serve(port=8766, output=Path('artifacts/capacity-lab')):
    if not 1024 <= port <= 65535:
        raise ValueError('Port must be 1024–65535')
    output = Path(output).resolve()
    jobs = {}
    lock = threading.Lock()
    web = Path(__file__).parent/'web'

    class Handler(BaseHTTPRequestHandler):
        def reply(self, value, status=200, mime='application/json'):
            data = json.dumps(value, allow_nan=False).encode() if mime == 'application/json' else value
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            host = self.headers.get('Host', '')
            if host not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                self.reply({'error': 'Invalid host'}, 403)
                return False
            origin = self.headers.get('Origin')
            if origin is not None and origin != f'http://{host}':
                self.reply({'error': 'Same-origin requests required'}, 403)
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in files:
                name, mime = files[path]
                self.reply((web/name).read_bytes(), mime=mime)
            elif path == '/api/defaults':
                self.reply(asdict(Profile()))
            elif path.startswith('/api/jobs/'):
                key = path.removeprefix('/api/jobs/')
                with lock:
                    job = dict(jobs[key]) if key in jobs else None
                self.reply(job if job else {'error': 'Unknown campaign'}, 200 if job else 404)
            else:
                self.reply({'error': 'Not found'}, 404)

        def do_POST(self):
            if not self.authorized():
                return
            if urlsplit(self.path).path != '/api/campaign':
                self.reply({'error': 'Not found'}, 404)
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply({'error': 'JSON required'}, 415)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 128000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                key = uuid.uuid4().hex
                args, profiles, total = request_config(body, output/key)
            except (ValueError, TypeError, KeyError) as error:
                self.reply({'error': str(error)}, 400)
                return
            with lock:
                if any(j['state'] == 'running' for j in jobs.values()):
                    self.reply({'error': 'A campaign is already running'}, 409)
                    return
                if len(jobs) >= 20:
                    jobs.pop(next(iter(jobs)))
                jobs[key] = dict(id=key, state='running', completed=0, total=total)

            def progress(completed, total):
                with lock:
                    jobs[key].update(completed=completed, total=total)

            def execute():
                try:
                    from .__main__ import run_campaign
                    result = run_campaign(args, profiles, progress)
                    with lock:
                        jobs[key].update(state='complete', summary=result, output=str(args.out))
                except Exception as error:
                    with lock:
                        jobs[key].update(state='failed', error=str(error))

            threading.Thread(target=execute, daemon=True).start()
            self.reply({'id': key}, 202)

        def log_message(self, fmt, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Airspace capacity research lab: http://127.0.0.1:{port}', flush=True)
    server.serve_forever()
