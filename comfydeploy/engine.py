"""ComfyDeploy: read-only discovery, manifest-based planning and approved installation.

No privileged action occurs from discover/plan/render. Execution is always explicit.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ROOT = Path.home() / '.comfydeploy'
BASE = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).resolve().parent / 'manifests' / 'components.json'


def run(*args, timeout=15):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
        return {'ok': p.returncode == 0, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()[-1200:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'stdout': '', 'stderr': str(exc)}


def probe(url, timeout=1.5):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ComfyDeploy/0.2'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {'online': 200 <= r.status < 400, 'status': r.status}
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        return {'online': False, 'detail': str(exc)[:140]}


def discovery(endpoints=None):
    endpoints = endpoints or {
        'comfyui': 'http://127.0.0.1:8188/system_stats',
        'llm': 'http://127.0.0.1:8001/v1/models',
    }
    docker = run('docker', 'info', '--format', '{{.ServerVersion}}')
    compose = run('docker', 'compose', 'version', '--short') if docker['ok'] else {'ok': False}
    gpu = run('nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader,nounits')
    cards = []
    for line in gpu['stdout'].splitlines() if gpu['ok'] else []:
        try:
            name, total, free = [s.strip() for s in line.rsplit(',', 2)]
            cards.append({'name': name, 'vram_mb': int(total), 'free_mb': int(free)})
        except ValueError:
            continue
    mounted = []
    if docker['ok']:
        containers = run('docker', 'ps', '--format', '{{.Names}}|{{.Image}}', timeout=8)
        if containers['ok']:
            mounted = [{'name': bits[0], 'image': bits[1]} for row in containers['stdout'].splitlines()
                       if len(bits := row.split('|', 1)) == 2]
    return {
        'platform': platform.platform(), 'hostname': platform.node(),
        'docker': docker['ok'], 'docker_version': docker.get('stdout', '') if docker['ok'] else '',
        'compose': compose['ok'], 'gpu': cards,
        'disk_free_gb': round(shutil.disk_usage(Path.home()).free / 1024**3, 1),
        'containers': mounted,
        'endpoints': {key: probe(url) for key, url in endpoints.items()},
        'timestamp': int(time.time()),
    }


def load_manifest(path=MANIFEST):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('components'), dict):
        raise ValueError('Unsupported component manifest schema')
    for name, comp in data['components'].items():
        if not name.replace('-', '').replace('_', '').isalnum():
            raise ValueError(f'Invalid component name: {name}')
        if comp.get('type') not in ('service', 'model', 'custom_node'):
            raise ValueError(f'Unsupported type for {name}')
        if comp['type'] == 'model' and not comp.get('sha256'):
            comp['unverified'] = True
    return data


def resolve(manifest, selected):
    resolved, visited, visiting = [], set(), set()
    def walk(name):
        if name in visited: return
        if name in visiting: raise ValueError('Dependency cycle at ' + name)
        if name not in manifest['components']: raise ValueError('Unknown component: ' + name)
        visiting.add(name)
        for dep in manifest['components'][name].get('requires', []): walk(dep)
        visiting.remove(name)
        visited.add(name)
        resolved.append(name)
    for name in selected: walk(name)
    return resolved


def _safe_model_path(root, rel):
    if not rel or Path(rel).is_absolute() or '..' in Path(rel).parts:
        raise ValueError('Invalid model destination')
    base = (Path(root) / 'models').resolve()
    dest = (base / rel).resolve()
    if not dest.is_relative_to(base): raise ValueError('Invalid model destination')
    return dest


def plan(manifest, selected, root, overrides=None):
    root = Path(root).expanduser().resolve()
    overrides = overrides or {}
    selected = list(dict.fromkeys(selected))
    resolved = resolve(manifest, selected)
    install_backend = bool(overrides.get('install_backend', 'comfyui' in resolved))
    reuse_backend = bool(overrides.get('reuse_backend', False))
    if reuse_backend: install_backend = False
    warnings, steps, bytes_required = [], [], 0
    if any(manifest['components'][c]['type'] == 'model' for c in resolved) and not install_backend:
        warnings.append('Model files are downloaded locally. Point an external ComfyUI at the model directory or share the directory volume.')
    for key in resolved:
        comp = manifest['components'][key]
        step = {'component': key, 'name': comp.get('name', key), 'type': comp['type'],
                'source': comp.get('url', comp.get('image', '')),
                'license': comp.get('license', 'Check upstream'),
                'unverified': comp.get('unverified', False),
                'action': 'download' if comp['type'] == 'model' else 'install' if comp['type'] == 'custom_node' else 'configure'}
        if comp['type'] == 'model':
            dest = _safe_model_path(root, comp['destination'])
            step['cached'] = dest.exists() and dest.is_file() and (not comp.get('sha256') or sha256(dest) == comp['sha256'])
            bytes_required += int(comp.get('size_bytes', 0)) if not step['cached'] else 0
            if step['unverified']: warnings.append(f'{key}: no published SHA-256 recorded; explicit permission is required to download')
        if comp['type'] == 'custom_node' and not comp.get('revision'):
            warnings.append(f'{key}: upstream Git reference is not pinned')
        steps.append(step)
    if not install_backend and any(s['type'] == 'custom_node' for s in steps):
        warnings.append('Custom nodes can only be installed automatically into a locally managed ComfyUI backend.')
    if install_backend: warnings.append('Local ComfyUI CUDA backend requires an NVIDIA GPU and Docker GPU toolkit; builds may download several GB.')
    return {
        'root': str(root), 'selected': selected, 'resolved': resolved, 'steps': steps,
        'install_backend': install_backend, 'reuse_backend': reuse_backend,
        'llm_url': overrides.get('llm_url', 'http://host.docker.internal:8001/v1'),
        'llm_model': overrides.get('llm_model', ''),
        'comfy_url': overrides.get('comfy_url', 'http://host.docker.internal:8188'),
        'estimated_download_bytes': bytes_required if bytes_required else None,
        'warnings': list(dict.fromkeys(warnings)), 'note': 'Preview only. Apply requires explicit approval.',
    }


def render(p):
    root = Path(p['root'])
    internal_comfy = 'http://comfyui:8188' if p['install_backend'] else p['comfy_url']
    config = {
        'serverUrl': internal_comfy,
        'llmProvider': 'custom',
        'llmConfigs': {'custom': {'url': p['llm_url'], 'model': p.get('llm_model', '')}},
        'threeD': {'enabled': 'pixal3d' in p['resolved'], 'pipeline': 'local'},
    }
    # The Studio image uses /configdir/config.json for persistent shared configuration.
    compose = '''name: comfydeploy
services:
  studio:
    image: ghcr.io/tiernan1979/comfyuistudio:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:5555:80"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./studio-config:/configdir
'''
    if p['install_backend']:
        compose += '''    depends_on:
      - comfyui
  comfyui:
    build:
      context: .
      dockerfile: Dockerfile.comfyui
    restart: unless-stopped
    gpus: all
    ports:
      - "127.0.0.1:8188:8188"
    volumes:
      - ./models:/opt/ComfyUI/models
      - ./custom_nodes:/opt/ComfyUI/custom_nodes
      - ./input:/opt/ComfyUI/input
      - ./output:/opt/ComfyUI/output
'''
    # Files under root are intentionally user inspectable and editable.
    dockerfile = '''FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
WORKDIR /opt/ComfyUI
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 && pip install --no-cache-dir -r requirements.txt
COPY entrypoint-comfyui.sh /usr/local/bin/comfydeploy-entrypoint
RUN chmod +x /usr/local/bin/comfydeploy-entrypoint
EXPOSE 8188
ENTRYPOINT ["/usr/local/bin/comfydeploy-entrypoint"]
'''
    entrypoint = '''#!/bin/sh
set -eu
# First-run custom nodes: optional requirements are installed when the container starts.
for req in /opt/ComfyUI/custom_nodes/*/requirements.txt; do
  [ -f "$req" ] || continue
  marker="${req}.comfydeploy-installed"
  if [ ! -e "$marker" ] || [ "$req" -nt "$marker" ]; then
    pip install --no-cache-dir -r "$req"
    touch "$marker"
  fi
done
exec python main.py --listen 0.0.0.0 --port 8188
'''
    return {
        'studio-config/config.json': json.dumps(config, indent=2) + '\n',
        'config.json': json.dumps(config, indent=2) + '\n',
        'compose.yaml': compose,
        **({'Dockerfile.comfyui': dockerfile, 'entrypoint-comfyui.sh': entrypoint} if p['install_backend'] else {}),
    }


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def download_model(component, dest, *, allow_unverified=False, emit=None):
    url = component['url']
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'huggingface.co', 'cdn-lfs.huggingface.co', 'github.com'}:
        raise ValueError('Model URL must use an approved HTTPS host')
    expected = component.get('sha256', '').lower()
    if not expected and not allow_unverified: raise ValueError('Unverified download requires explicit approval')
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and (not expected or sha256(dest) == expected): return 'cached'
    temp = dest.with_suffix(dest.suffix + '.part')
    start = temp.stat().st_size if temp.exists() else 0
    req = urllib.request.Request(url, headers={
        'User-Agent': 'ComfyDeploy/0.2', **({'Range': f'bytes={start}-'} if start else {})})
    with urllib.request.urlopen(req, timeout=60) as response:
        append = bool(start and response.status == 206)
        if not append: start = 0
        with temp.open('ab' if append else 'wb') as out:
            current = start
            while block := response.read(1024 * 1024):
                out.write(block)
                current += len(block)
                if emit and (current - start) % (16 * 1024 * 1024) < len(block):
                    emit({'kind': 'progress', 'bytes': current, 'file': dest.name})
    if expected and sha256(temp) != expected:
        temp.unlink(missing_ok=True)
        raise ValueError('SHA-256 mismatch')
    temp.replace(dest)
    return 'downloaded'


def _install_custom_node(comp, root):
    if not comp.get('url', '').startswith('https://github.com/'):
        raise ValueError('Custom node source must be GitHub HTTPS')
    name = comp['directory']
    if '/' in name or '\\' in name or name in ('.', '..'): raise ValueError('Invalid custom node directory')
    target = root / 'custom_nodes' / name
    if target.exists(): return 'already installed'
    target.parent.mkdir(parents=True, exist_ok=True)
    args = ['git', 'clone', '--depth', '1']
    if comp.get('revision'): args.extend(['--branch', comp['revision']])
    args.extend([comp['url'], str(target)])
    result = run(*args, timeout=300)
    if not result['ok']:
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(result['stderr'])
    return 'cloned'


def apply(p, manifest, approve=False, allow_unverified=False, start=False, emit=None):
    if not approve: raise ValueError('Explicit install approval required')
    root = Path(p['root']); root.mkdir(parents=True, exist_ok=True)
    for name, content in render(p).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_text(encoding='utf-8') == content: continue
        if target.exists():
            stamp = time.strftime('%Y%m%d-%H%M%S')
            shutil.copy2(target, target.with_name(target.name + '.' + stamp + '.bak'))
        target.write_text(content, encoding='utf-8')
    results = []
    for step in p['steps']:
        name = step['component']; comp = manifest['components'][name]
        if emit: emit({'kind': 'step', 'component': name, 'message': f'Processing {name}'})
        try:
            if step['type'] == 'model':
                target = _safe_model_path(root, comp['destination'])
                outcome = download_model(comp, target, allow_unverified=allow_unverified, emit=emit)
            elif step['type'] == 'custom_node':
                if not p['install_backend']: outcome = 'skipped (external ComfyUI)'
                else: outcome = _install_custom_node(comp, root)
            else: outcome = 'configured'
            result = {'component': name, 'status': outcome, 'ok': True}
        except Exception as exc:
            result = {'component': name, 'status': str(exc), 'ok': False}
        results.append(result)
        if emit: emit({'kind': 'result', **result})
    if start and all(r['ok'] for r in results):
        if emit: emit({'kind': 'step', 'component': 'docker', 'message': 'Starting Compose stack'})
        proc = run('docker', 'compose', '-f', str(root / 'compose.yaml'), 'up', '-d', '--build', timeout=1800)
        results.append({'component': 'docker', 'status': 'started' if proc['ok'] else proc['stderr'], 'ok': proc['ok']})
    report = {'root': str(root), 'results': results, 'success': all(r['ok'] for r in results), 'timestamp': int(time.time())}
    (root / 'last-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
