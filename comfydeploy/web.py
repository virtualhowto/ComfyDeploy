"""Local-first web control plane. No arbitrary shell execution or unauthenticated LAN access."""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine import DEFAULT_ROOT, MANIFEST, apply, discovery, load_manifest, plan

UI_DIR = Path(__file__).resolve().parent / 'ui'


class ControlPlane:
    def __init__(self, root=DEFAULT_ROOT, manifest=MANIFEST):
        self.root = Path(root).expanduser().resolve()
        self.manifest = load_manifest(manifest)
        self.lock = threading.Lock()
        self.jobs = {}
        self.active_id = None

    def make_plan(self, payload):
        pack_ids = payload.get('packs', ['base'])
        if not isinstance(pack_ids, list) or len(pack_ids) > 12: raise ValueError('Invalid packs')
        packs = {p['id']: p for p in self.manifest['packs']}
        selected = []
        for pack_id in pack_ids:
            if pack_id not in packs: raise ValueError(f'Unknown pack: {pack_id}')
            selected.extend(packs[pack_id]['components'])
        if 'studio' not in selected: selected.insert(0, 'studio')
        opts = payload.get('options') or {}
        if not isinstance(opts, dict): raise ValueError('Invalid options')
        for key in ['llm_url', 'comfy_url']:
            if key in opts:
                parsed = urlsplit(opts[key])
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError(f'Invalid {key}')
        if len(str(opts.get('llm_model', ''))) > 180: raise ValueError('Model alias too long')
        if opts.get('reuse_backend') and 'comfyui' in selected:
            selected.remove('comfyui')
            # Model dependencies on comfyui are kept in the plan for source provenance;
            # they do not cause Docker backend deployment while reuse_backend is enabled.
        return plan(self.manifest, selected, self.root, opts)

    def start_job(self, payload):
        if payload.get('approve') is not True: raise ValueError('Deployment approval required')
        p = self.make_plan(payload)
        with self.lock:
            if self.active_id and self.jobs[self.active_id]['status'] == 'running':
                raise ValueError('Another installation is already running')
            job_id = secrets.token_hex(6)
            job = {'id': job_id, 'status': 'running', 'created_at': int(time.time()), 'events': [], 'report': None}
            self.jobs[job_id] = job
            self.active_id = job_id
        def worker():
            def emit(event):
                with self.lock:
                    job['events'].append({'time': int(time.time()), **event})
                    job['events'] = job['events'][-500:]
            try:
                job['report'] = apply(p, self.manifest, approve=True,
                                      allow_unverified=payload.get('allow_unverified') is True,
                                      start=payload.get('start') is True, emit=emit)
                job['status'] = 'complete' if job['report']['success'] else 'failed'
            except Exception as exc:
                emit({'kind': 'error', 'message': str(exc)})
                job['status'] = 'failed'
            finally:
                with self.lock: self.active_id = None
        threading.Thread(target=worker, daemon=True).start()
        return {'job_id': job_id}


def serve(bind='127.0.0.1', port=7862, token=None, root=DEFAULT_ROOT):
    if bind not in ('127.0.0.1', '::1', 'localhost') and not token:
        raise ValueError('Non-loopback binding requires --token or COMFYDEPLOY_TOKEN')
    plane = ControlPlane(root=root)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'ComfyDeploy/0.2'
        def log_message(self, fmt, *args): pass

        def _auth(self):
            if not token: return True
            supplied = self.headers.get('Authorization', '')
            return hmac.compare_digest(supplied, f'Bearer {token}')

        def _json(self, data, code=200):
            body = json.dumps(data, separators=(',', ':'), default=str).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, code, message): self._json({'error': message}, code)

        def _api(self, method):
            if not self._auth(): return self._error(401, 'Access token required')
            try:
                if method == 'GET':
                    if self.path == '/api/catalog': return self._json(plane.manifest)
                    if self.path == '/api/discover': return self._json(discovery())
                    if self.path == '/api/jobs':
                        return self._json({'jobs': list(reversed(list(plane.jobs.values())))[0:20]})
                    if self.path.startswith('/api/jobs/'):
                        item = plane.jobs.get(self.path.split('/')[-1])
                        return self._json(item) if item else self._error(404, 'Unknown job')
                    return self._error(404, 'Not found')
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 131072: return self._error(413, 'Invalid request size')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict): raise ValueError('JSON object required')
                if self.path == '/api/plan': return self._json(plane.make_plan(payload))
                if self.path == '/api/apply': return self._json(plane.start_job(payload), 202)
                return self._error(404, 'Not found')
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                return self._error(400, str(exc))
            except Exception:
                return self._error(500, 'Internal server error')

        def do_GET(self):
            if self.path.startswith('/api/'): return self._api('GET')
            assets = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
                      '/styles.css': ('styles.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}
            if self.path not in assets: return self._error(404, 'Not found')
            name, mime = assets[self.path]
            data = (UI_DIR / name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path.startswith('/api/'): return self._api('POST')
            return self._error(404, 'Not found')

    httpd = ThreadingHTTPServer((bind, port), Handler)
    print(f'ComfyDeploy console: http://{bind}:{port} (root: {plane.root})', flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally: httpd.server_close()
