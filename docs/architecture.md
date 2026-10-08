# ComfyDeploy architecture

## Components

- **Browser dashboard:** a static HTML, CSS and JS UI, no external assets or CDN.
- **Control plane:** Python stdlib HTTP on `127.0.0.1:7862`, optional bearer token mandatory for non-loopback.
- **Planner:** manifest schema v1, dependency DAG, cached-file detection, explicit warnings.
- **Executor:** opt-in model downloader, custom-node Git installer, generated backend Dockerfile, Compose start and event reporter.
- **Outputs:** `~/.comfydeploy/{compose.yaml,Dockerfile.comfyui,entrypoint-comfyui.sh,studio-config/config.json,models/,custom_nodes/,input/,output/,last-report.json}`.

## Deployment trust boundary

The control plane runs with the permissions of its host user; it intentionally does not expose generic shell execution. Docker requires privileged access granted to that user. Limit who can access the HTTP service and use TLS, SSO, network segmentation and a dedicated deploy agent before exposing remotely.

## Integration

Studio proxy targets `http://comfyui:8188` when managed, or a configured external ComfyUI endpoint. Studio's custom LLM provider URL may point to an existing Unsloth/llama.cpp OpenAI-compatible endpoint, e.g. `http://host.docker.internal:8001/v1`.

## Honest limits

3D manifest covers only an initial subset; downstream UniRig / Paint assets and some weights must be obtained per upstream instructions. New ComfyUI backend builds are not yet pinned, custom nodes may run install-time code, and Docker/GPU integration has not been validated in a real NVIDIA host during this build.
