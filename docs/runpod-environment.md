# Runpod template environment

Synced to account template **Flux 2 Image ComfyUI One-Click** (`3l6xecpzep`) on 2026-10-30.

[Open template](https://console.runpod.io/deploy?template=3l6xecpzep)

There are three Pod templates, one per container generation. They share everything except the name, image tag, `STUDIO_VERSION` and `MODEL_MODE`; `config/runpod-template.json` is the `:2` template and `config/runpod-generations.json` holds the overrides for the others. Create or update one with `python3 scripts/create-runpod-template.py --generation 1|2|3`.

| Template | Id | Image | `MODEL_MODE` |
| --- | --- | --- | --- |
| Flux 1 Image ComfyUI One-Click | `hrf2a1d7f7` | `:1` | `dev` |
| Flux 2 Image ComfyUI One-Click | `3l6xecpzep` | `:2` | `dev` |
| Flux 3 Image ComfyUI Klein One-Click | `0gayum1now` | `:3` | `distilled` |

Image: `ghcr.io/acdevmedia/flux-comfyui:2`. Container disk: **200 GB**. Workspace: `/workspace`. Template service: `8188/http` (ComfyUI) and `3923/http` (copyparty). The gateway port 8000 is used by the Hub/Serverless listing only and is not exposed by the Pod template. No persistent volume is requested; `volumeInGb` is 0 and storage is temporary.

`config/runpod-template.json` holds the Pod defaults. `.runpod/template-source.json` records the account source. `.runpod/hub.json` exposes the same values through Hub inputs or fixed values. `.runpod/tests.json` uses the same defaults for readiness tests. `.runpod/test_template_sync.py` fails if any of those four files, this document or the README drift apart.

## Credentials

The file browser on port 3923 signs in with Runpod Secrets `COPYPARTY_USERNAME` and `COPYPARTY_SECRET`, which the template maps to `COPYPARTY_USERNAME` and `COPYPARTY_PASSWORD`.

**Only the `:3` tag (FLUX 3) needs a token.** FLUX.1 and FLUX.2 download anonymously, so the default `:2` Pod needs no Hugging Face account. For `:3`, create Runpod Secret `HUGGINGFACE_TOKEN` with a Hugging Face read token, using the account that accepted the gated model agreement for `black-forest-labs/flux-3-image-klein-comfy`. Secret references are passed through unchanged; no credential values are stored in this repository or baked into the image.

## Template variables

### `COPYPARTY_USERNAME`

Default: `{{ RUNPOD_SECRET_COPYPARTY_USERNAME }}`.

Username for the output file browser on port 3923, from Runpod Secret `COPYPARTY_USERNAME`.

### `COPYPARTY_PASSWORD`

Default: `{{ RUNPOD_SECRET_COPYPARTY_SECRET }}`.

Password for the output file browser, from Runpod Secret `COPYPARTY_SECRET`. Without both values the file browser does not start; ComfyUI is unaffected.

### `HF_TOKEN`

Default: `{{ RUNPOD_SECRET_HUGGINGFACE_TOKEN }}`.

Hugging Face read token supplied through the Runpod Secret HUGGINGFACE_TOKEN. Required only for the gated `:3` generation, where the repository agreement must be accepted by the same account before first boot; ignored by `:1` and `:2`.

### `HF_HOME`

Default: `/workspace/.cache/huggingface`.

Hugging Face cache and metadata directory on container storage.

### `MODEL_MODE`

Default: `dev`.

Which variant of the generation to download. On FLUX.2 that is `dev` (the full model, about 56.6 GB resident) or `turbo` (Klein 4B, about 23.9 GB), and `both` fetches everything, roughly 80 GB. Shared components such as the VAE download either way.

### `STUDIO_VERSION`

Default: `2`.

Which model generation this image serves, matching `versions/2/`. It is baked at build time and selects both the weights downloaded on first boot and the workflows installed. Deploy the `:1` or `:3` tag for another generation rather than changing this on a running Pod.

### `PORT`

Default: `8000`.

Gateway HTTP and WebSocket port served by `.runpod/handler.py`. ComfyUI itself stays on 8188.

### `PORT_HEALTH`

Default: `8001`.

Readiness port. `/ping` returns 503 until ComfyUI reports device information, then 200.

## Hub additions and differences

The Pod template and the Hub listing build from the same Dockerfile and the same defaults. The Hub listing runs the readiness test in `.runpod/tests.json` on a 48 GB L40S with CUDA 12.8–13.0; that test establishes that the service starts and answers, not that generation quality is acceptable. A Serverless browser session requires exactly one active worker and authenticated HTTP and WebSocket access, as described in `.runpod/README.md`.

Workflow defaults apply to newly installed workflow files; existing user edits in `/workspace` are preserved across restarts.

## Account template metadata

Visibility: public. No custom entrypoint or start command is set; the image entrypoint supervises ComfyUI through the gateway handler. `startJupyter` and `startSsh` are false. SSH starts inside the container only when `PUBLIC_KEY` is supplied, and the template does not expose port 2222.
