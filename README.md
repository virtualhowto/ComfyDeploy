# ComfyDeploy ✦

**A local-first control plane for self-hosted creative AI.** Select features; ComfyDeploy resolves the dependencies, builds a deployment plan, downloads model weights, configures ComfyUI Studio, and optionally starts a locally managed ComfyUI stack.

The dashboard is a purpose-built responsive web interface. Everything important—Docker/GPU discovery, component selection, endpoint integration, dry-run warnings, approval and live installation logs—is powered by the local Python API, not simulated data.

> **Status: v0.2 developer preview.** Test on a non-production host first. No Docker or GPU workloads were available in the development environment to verify generation end-to-end.

## Run the web dashboard

Requires Python 3.10+; no runtime pip dependencies.

```bash
python3 -m comfydeploy web
# Open http://127.0.0.1:7862
```

To install as a command:

```bash
pip install .
comfydeploy web
```

To allow access from another machine, **set a token and put the console behind TLS/authentication**:

```bash
COMFYDEPLOY_TOKEN='use-a-long-random-secret' comfydeploy web --bind 0.0.0.0 --port 7862
```

Never expose the control plane unauthenticated to the internet. The browser prompts for the token; it is kept in the tab session. CORS is not enabled.

## What works

- Dark responsive dashboard, component catalogue, five-stage deployment wizard and deployment logs.
- Read-only host discovery (Docker, Compose, NVIDIA VRAM, disk, running containers, ComfyUI and LLM endpoints).
- Seven capability packs: core, images, editing, video, music, 3D and upscale.
- Versioned manifest with dependencies, model paths and upstream source URLs.
- Safe dry-run preview including unverified model warnings.
- Explicit deployment approval and separate unchecked-consent for model downloads without SHA-256.
- Downloads from curated HTTPS sources, `.part` resume, optional SHA-256 verification, caching.
- Opt-in Git custom-node installation, ComfyUI Dockerfile, persistent bind mounts and Docker Compose deployment.
- Studio configuration automatically written into its persistent `/configdir/config.json` folder.
- ComfyUI service URL automatically set to its Compose hostname for managed deployment; OpenAI-compatible endpoint supports Unsloth / llama.cpp.
- In-memory asynchronous job tracking and `last-report.json` saved to installation directory.
- CLI for headless discovery, planning, render, approved installation.

## CLI

```bash
python3 -m comfydeploy discover
python3 -m comfydeploy catalog
python3 -m comfydeploy plan --with studio --with qwen-image
python3 -m comfydeploy install --with studio --approve --start
# WARNING: downloads without published SHA-256 need separate opt-in
python3 -m comfydeploy install --with studio --with qwen-image --approve --allow-unverified-models --start
```

Data lives at `~/.comfydeploy` unless overridden using `--root`. Studio listens on **127.0.0.1:5555**, and a locally managed ComfyUI backend on **127.0.0.1:8188**. Deploying CUDA-backed ComfyUI requires Docker Compose, NVIDIA drivers and NVIDIA Container Toolkit.

## Constraints and safety

- **Model downloads are large.** No automatic download happens before explicit approval; disk/VRAM estimates are incomplete because upstream file sizes vary.
- **Upstream revisions are not all pinned.** The generated ComfyUI Dockerfile clones current upstream and Studio uses `latest`. Review/pin before production use.
- **Third-party custom nodes can execute arbitrary code.** Only install nodes you trust; explicit approval is required and external licence terms apply.
- **3D is experimental.** Pixal3D may need additional image encoders, rigging weights, tools and GPU resources not yet represented in the current manifest; inspect upstream docs before relying on it.
- **Reusing external ComfyUI:** downloaded models remain in the local `models/` directory. Make that directory available to the existing backend and restart it if required.
- **No arbitrary command API.** Web service provides only catalogue, discovery, plan, approved apply and job status; do not expose a Docker socket to browsers.
- **Authentication:** loopback default; non-loopback binding requires a bearer token. A production-grade reverse proxy + SSO/RBAC and audit log are still planned.
- **Versioning/rollback:** changed generated config files are backed up with timestamps; full transactional rollback and job resume are not implemented yet.
- **GPU scheduling:** shared GPU VRAM arbitration between Unsloth and ComfyUI is not implemented; use model unloading or separate workers.

## Architecture

`Web UI → Python HTTP control plane → environment probe → pack resolver → approval → downloads / node installer → Compose → job events / report`

The original [ComfyUI Studio](https://github.com/tiernan1979/comfyuistudio) remains independent. See [architecture](docs/architecture.md).

## Tests

```bash
python3 -m unittest discover -s tests -v
node --check comfydeploy/ui/app.js
```

## Roadmap

1. Hard-pin ComfyUI, Studio and all custom-node commits, plus integrity and licence metadata.
2. Improved capability preflight: model inventories and VRAM/disk checks before apply.
3. Fully automated 3D dependencies and actual test-generation validation.
4. Authentik/Traefik adapter, RBAC, long-lived audit log, remote workers and rollback.
5. Support offline downloads, model registry mirroring and multi-GPU scheduling.

MIT-licensed installer project. Upstream tools and model weights retain their own licences.
