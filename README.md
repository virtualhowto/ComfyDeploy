# ComfyDeploy

Environment-aware deployment manager for [ComfyUI Studio](https://github.com/tiernan1979/comfyuistudio) and its optional AI stack.

## Goals

- Discover Docker, GPU, storage, ComfyUI and OpenAI-compatible LLM endpoints (including Unsloth / llama.cpp).
- Reuse existing services rather than reinstalling them.
- Offer selectable image, image-edit, video, music and image-to-3D capability packs.
- Resolve and download required model files and custom-node dependencies.
- Generate durable Docker Compose and ComfyUI Studio configuration.
- Support dry-run, idempotent apply, repair, upgrades and rollback.

## Status

**Early project bootstrap.** The complete starter source bundle is available in the originating ChatGPT conversation. GitHub content will be expanded from this initial scaffold. Not production-ready.

## Architectural principles

- Version-pinned component manifests and checksum validation.
- Dry-run plans before privileged changes.
- No Docker socket exposed to a browser.
- No automatic public exposure or alteration of existing proxy / SSO configuration.
- Persist models outside disposable containers.
- Warn before large downloads and GPU-memory conflicts.

## Proposed modules

`discovery` → `capability resolver` → `dependency planner` → `download/cache` → `Compose/config renderer` → `deployment & verification`.

## Upstream

ComfyUI Studio is a separate MIT-licensed project. This repository is an independent deployment wrapper, not an upstream fork.
