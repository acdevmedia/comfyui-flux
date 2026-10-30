# Flux 3 Image ComfyUI Klein One-Click

[![Runpod](https://api.runpod.io/badge/acdevmedia/comfyui-flux)](https://console.runpod.io/hub/listing/acdevmedia/comfyui-flux)

FLUX 3 Image Klein: native ComfyUI base and distilled text-to-image generation, with optional prompt expansion and advanced image-editing graphs.

Container: **`ghcr.io/acdevmedia/flux-comfyui:3`**. Image releases also receive a version tag (`3.0.0`) and an immutable `sha-<commit>` tag. Source pins, model revisions and checksums live under `versions/3/`. New model generations get their own profile and container major tag; rebuilds retain the model family tag and always get a new commit tag.

## Start on Runpod

1. Sign in to Hugging Face and accept the model access agreements for each linked repository using the account that owns your token:
   - [black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy)
   Agreements apply separately to each repository. Accepting one does not grant access to the others.
2. Create a Hugging Face **read** token and add it to Runpod Secrets as **HUGGINGFACE_TOKEN**. The template maps this secret to `HF_TOKEN`; do not paste credentials into public template fields.
3. Create/update the template with `python3 scripts/create-runpod-template.py`. Use `--dry-run` to review its payload. This small API helper reads the ignored local `.env`; it does not build an image or download models.
4. Launch on a **48 GB** GPU with a **200 GB container disk** and no persistent volume. **L40S** and **A40** are both validated; the L40S is roughly twice as fast for this workload, and **RTX A6000** is the other 48 GB option. Peak residency is about 21 GB: one transformer, the Qwen3-VL text encoder, the prompt upsampler and the VAE. A 24 GB card is not enough; an 80 GB A100 is not required and costs several times as much. First boot downloads the pinned weights into `/workspace/ComfyUI/models`.
5. Open **Connect → HTTP 8188 / ComfyUI**. The template exposes ComfyUI only; the service reports Ready once the weights finish downloading. If the Connect link returns **HTTP 403**, open a blank tab and paste `https://<pod-id>-8188.proxy.runpod.net` into the address bar — see Troubleshooting. No additional installation is required.
6. In the workflow sidebar, choose the base or distilled workflow, edit the prompt and shot settings, and click Queue. Save generated images before deleting/replacing the Pod.

Storage is temporary. The template does not attach a network volume. First-boot downloads are resumable, existing workflow edits are preserved, and no model weights or credentials are baked into the container.

## Simple workflows

- **01 Distilled Text to Image:** 16 steps, guidance 1.0, Euler/simple, 1280 × 720. Fast iteration.
- **02 Base Text to Image:** 50 steps, guidance 3.5, Euler/simple, 1280 × 720. Undistilled checkpoint.
- **03–04 Image Edit:** upload a picture and describe the changes; uses the same base or distilled checkpoint as generation.
- **10–13 Advanced:** editable upstream ComfyUI graphs for text generation and reference-image editing. Upload your own image for editing; example asset names are placeholders.

The simple node exposes prompt, negative prompt, mode, dimensions, seed, steps, guidance, sampler, schedule, prompt upsampling and its token budget. Canvas defaults to **1280 × 720**.

A broad general-purpose **negative prompt** is filled in by default, covering optical defects, exposure and colour faults, anatomy errors, framing mistakes, and overlays such as watermarks, signatures, captions and UI furniture. Clear or edit it freely. It applies **only when guidance is above 1.0**: the distilled path runs at guidance 1.0 with no effective CFG branch, so the field is ignored there and the node passes an empty negative rather than pretending otherwise. Long keyword-style negatives are a weaker lever on a flow-matching model with a language-model text encoder than they were on older checkpoints; a short, specific negative usually beats a long one. It expands into native loader, text-generation, sampler and decode nodes. Prompt expansion runs locally through the pinned Qwen3.5 9B upsampler and is **off by default**. It is a second large model: 9.75 GB of weights that must be resident alongside the transformer and text encoder, and on a 48 GB card the three compete, so ComfyUI swaps models between the expansion pass and sampling. Enabling it can add minutes per image. Turn it on when you want a short prompt fleshed out and can accept the cost; write a detailed prompt yourself and leave it off for fast iteration. Model precision is INT8 ConvRot for the transformer and text encoders; precision and distillation are separate choices. Native ComfyUI offloading controls model residency.

The advanced graphs preserve the official template structure, with the upsampler filename changed from W4A8 to the downloaded INT8 checkpoint. Original system prompt and graph sources: [Comfy-Org templates](https://github.com/Comfy-Org/workflow_templates/tree/abb9cf6477b59c52dbe234c67f82318dadd872b2/templates), [BFL ComfyUI model card](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy).

## Seeds

The seed widget carries ComfyUI's standard **control after generate** control, set to `randomize` in every packaged workflow, so each run uses a new seed. Set it to `fixed` to reproduce an exact image, or `increment` to walk a series. Earlier releases pinned the seed at 42 with the control disabled, which made every run of a workflow produce the same picture.

## Image preview ribbon

A strip of recent output images sits along the bottom of the ComfyUI window and refreshes as each queued graph finishes, so you can queue a long batch and watch it fill.

Click any thumbnail to open the viewer. **Left and right arrow keys** move through the batch, **space** picks the current image, **D** downloads it and **Escape** closes. The tick in the corner of a thumbnail picks it without opening the viewer. **Download picked** then saves just those files, which is the point: queue fifty, skim them, keep the three that worked.

Picks live for the session and are never uploaded. The ribbon reads the recent `/history` entries through ComfyUI's own `/view` endpoint, skips transient previews, and never scans the output directory.

## Environment variables

- `HF_TOKEN`: Hugging Face read credential, mapped to `{{ RUNPOD_SECRET_HUGGINGFACE_TOKEN }}`. Required; access must be approved for each gated repository.
- `HF_HOME=/workspace/.cache/huggingface`: Hugging Face cache/metadata location.
- `MODEL_MODE=both`: download both variants. `base` or `distilled` limits first-boot downloads. Both variants share the pinned text encoders, prompt upsampler and VAE, so neither choice skips those components.
- `STUDIO_VERSION=3`: baked profile identity; changing this does not install another model generation.
- `PORT=8000`: gateway HTTP port used by the Runpod Hub/Serverless listing. The Pod template does not expose it; Pod users reach ComfyUI directly on 8188.
- `PORT_HEALTH=8001`: readiness service used by the Hub listing; `/ping` returns 503 until ComfyUI responds with device information. Not exposed by the Pod template.
- `OMP_NUM_THREADS=8`, `MKL_NUM_THREADS=8`: runtime CPU-thread defaults; override to match the Pod's allocated CPU quota.
- `PUBLIC_KEY`: optional SSH public key for diagnostics. When present, the container starts SSH on port 2222; the template does not expose this port. The disposable Actions test exposes it only for its ephemeral key.

`RUNPOD_API_KEY` and `GITHUB_PACKAGES_PAT` are local deployment credentials only; never pass them into the worker container. GitHub Actions uses repository secrets for Runpod validation. The account's existing GHCR registry authorization is supplied separately to disposable test Pods where required.

## Build, validate and update

All container builds and runtime tests run in **GitHub Actions**. Do not build on the local workstation. Push to `develop` or `main`, or dispatch the build workflow. Paid GPU tests are opt-in through the `gpu_smoke` dispatch input; ordinary pushes build and run CPU checks only. The workflow runs source checks, builds on an Actions runner, starts a CPU-only ComfyUI service inside the build to verify graph schemas, then publishes the image. When dispatched with `gpu_smoke=true`, it launches a disposable 48 GB L40S Pod using that exact image digest (override with `VALIDATION_GPU_TYPES`) and generates a 512×512 image and an image-edit result with each checkpoint, grouping each pair to keep that model loaded. Validation checks dimensions, pixel variance and entropy; these detect blank outputs, not artistic quality. PNGs, system metadata and results are uploaded as Actions artifacts. A `finally` block and an unconditional cleanup step delete the test Pod.

The package must be public on GHCR for anonymous template users; account registry credentials can support private validation. Configure Actions secrets `RUNPOD_API_KEY` and, if needed, `RUNPOD_REGISTRY_AUTH_ID`. The `.runpod` listing uses the same image build and environment defaults; its required readiness test does not replace the GPU generation tests. For Serverless browser use, keep exactly one active worker and supply Runpod authentication on HTTP and WebSocket requests. The Pod template is the straightforward browser deployment.

Build and GPU-validation status must be confirmed in Actions before treating a revision as tested. Captured package versions are stored in `/opt/acdev/python-lock.txt` inside each image. To update a model generation, add a new version profile, regenerate its workflow defaults and manifests, update the corresponding container tags, and repeat the remote tests. No runtime dependency upgrades or branch-head model downloads occur during Pod startup.

## Image editing and model reuse

The simple FLUX node also has an optional reference-image socket. Connect an uploaded image to enable instruction-based editing; disconnect it for text-to-image. The image is encoded with the same VAE and attached as native reference conditioning. The local prompt upsampler sees the image when connected. Loader identities and filenames are shared across paired workflows so ComfyUI can reuse cached models. Switching between base and distilled selects different checkpoints.

## Troubleshooting

- **Connect opens ComfyUI with HTTP 403:** ComfyUI's browser-origin guard rejects cross-site page navigations, and a link clicked from the Runpod dashboard or any other site counts as cross-site. This image patches the guard at build time to permit only a safe top-level `GET /` navigation; cross-site API, WebSocket, form and subresource requests stay blocked. On a Pod built from an older digest, open a blank tab and paste `https://<pod-id>-8188.proxy.runpod.net` into the address bar, which the browser sends as a same-origin navigation.
- **Connect shows ERR_INVALID_RESPONSE:** the same 403, returned with a body the browser cannot render. Treat it as the entry above.
- **ComfyUI does not become ready:** first boot downloads the pinned weights before ComfyUI starts. Check the Pod logs; the service answers only after it reports device information.
- **Out of GPU memory:** use a 48 GB card. A 24 GB card cannot hold the distilled path.
