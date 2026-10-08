"""ComfyDeploy command line and local control plane."""
import argparse
import json
from pathlib import Path

from .engine import DEFAULT_ROOT, MANIFEST, apply, discovery, load_manifest, plan, render


def main():
    parser = argparse.ArgumentParser(prog='comfydeploy', description='ComfyUI Studio deployment manager')
    parser.add_argument('command', choices=['web', 'discover', 'catalog', 'plan', 'install', 'render'])
    parser.add_argument('--manifest', default=str(MANIFEST))
    parser.add_argument('--root', default=str(DEFAULT_ROOT))
    parser.add_argument('--with', dest='components', action='append', default=[])
    parser.add_argument('--llm-url', default='http://host.docker.internal:8001/v1')
    parser.add_argument('--llm-model', default='')
    parser.add_argument('--comfy-url', default='http://host.docker.internal:8188')
    parser.add_argument('--reuse-backend', action='store_true')
    parser.add_argument('--approve', action='store_true')
    parser.add_argument('--allow-unverified-models', action='store_true')
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=7862)
    parser.add_argument('--token', default=None, help='Access token (also COMFYDEPLOY_TOKEN)')
    args = parser.parse_args()
    if args.command == 'web':
        import os
        from .web import serve
        serve(bind=args.bind, port=args.port, token=args.token or os.getenv('COMFYDEPLOY_TOKEN'), root=args.root)
        return
    if args.command == 'discover': result = discovery()
    else:
        manifest = load_manifest(args.manifest)
        if args.command == 'catalog': result = manifest
        else:
            p = plan(manifest, args.components or ['studio'], args.root, {
                'llm_url': args.llm_url, 'llm_model': args.llm_model,
                'comfy_url': args.comfy_url, 'reuse_backend': args.reuse_backend})
            if args.command == 'plan': result = p
            elif args.command == 'render': result = render(p)
            else: result = apply(p, manifest, approve=args.approve,
                                 allow_unverified=args.allow_unverified_models, start=args.start)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
