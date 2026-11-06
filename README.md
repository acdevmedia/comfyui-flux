# Flux Image ComfyUI One-Click

[![Runpod](https://api.runpod.io/badge/acdevmedia/comfyui-flux)](https://console.runpod.io/hub/listing/acdevmedia/comfyui-flux)

FLUX on ComfyUI: one repository for FLUX.1, FLUX.2 and FLUX 3 Klein, each with text-to-image and image-to-image. FLUX.2 (`dev`, or the fast Klein 4B "turbo" variant) is the default; FLUX.1 and the gated FLUX 3 Klein are other container tags.

## Model generations

One repository, one image build, three containers — the tag selects which generation of weights the Pod downloads and which workflows it installs.

| Tag | Generation | Variants | Resident | GPU |
| --- | --- | --- | --- | --- |
| `:2` | **FLUX.2** (default) | `dev` (default), `turbo` = Klein 4B | 56.6 GB / 23.9 GB | 80 GB for dev, 48 GB for turbo |
| `:3` | FLUX 3 Image Klein | base, distilled | 26.6 GB | 48 GB |
| `:1` | FLUX.1 | dev, schnell | 34.5 GB | 48 GB |

`MODEL_MODE` picks the variant, so a `:2` Pod downloads only what it needs: `dev` for the full model, `turbo` for Klein 4B, `both` for roughly 80 GB of weights.

**FLUX.2 `dev` needs an 80 GB card** (tested on an A100 80 GB). Its resident set is about 56.6 GB — a 35.5 GB transformer, an 18 GB Mistral text encoder, the VAE and the Turbo LoRA — which does not fit 48 GB. Deploy dev on an H100 or A100 80 GB, or set `MODEL_MODE=turbo` and run Klein 4B on a 48 GB card.

There is no open-weight **FLUX.2 Ultra** or **pro**: those are Black Forest Labs' hosted API tiers. The published FLUX.2 line is `dev` plus the Klein family, and `dev` is the strongest of them.

Each tag is the same image with a different baked `STUDIO_VERSION`; nothing model-specific is in the layers. **FLUX.2 (`:2`) and FLUX 3 (`:3`) have been run on a GPU; FLUX.1 (`:1`) has not.** FLUX.1 ships pinned weights, checksums and an upstream-derived workflow and passes the source and reference checks, but nothing has rendered an image from it. `docs/VALIDATION.md` records exactly what ran on which card, and what it does and does not show.

Not included, and why: FLUX.1 Kontext, Fill, Depth, Canny and Redux need text encoders no longer published in a ComfyUI-packaged repository; FLUX.2 Klein 9B has no diffusion weights in its ComfyUI repository.

Container: **`ghcr.io/acdevmedia/flux-comfyui:2`** (the Pod template default; use `:1` or `:3` for the other generations). Image releases also receive a version tag (`2.0.0`) and an immutable `sha-<commit>` tag. Source pins, model revisions and checksums live under `versions/3/`. New model generations get their own profile and container major tag; rebuilds retain the model family tag and always get a new commit tag.

## Start on Runpod

1. Create or update the template with `python3 scripts/create-runpod-template.py`, or `--dry-run` to review the payload first. It only calls the Runpod API; it builds nothing and downloads no weights.
2. **Pick a card for the variant you want:**

   | Tag and variant | Needs | Validated on |
   | --- | --- | --- |
   | `:2` **FLUX.2 dev** (the default) | **80 GB**, about 56.6 GB resident | A100 80 GB |
   | `:2` `MODEL_MODE=turbo` (Klein 4B) | 48 GB, about 24 GB resident | A40 |
   | `:3` FLUX 3 | 48 GB, about 21 GB resident | L40S, A40 |
   | `:1` FLUX.1 | 48 GB | not run |

   Use a **200 GB container disk** and no persistent volume, or 300 GB if you load both FLUX.2 variants. A 24 GB card is not enough for any of them. First boot downloads the pinned weights into `/workspace/ComfyUI/models`.
3. **Only for `:3` (FLUX 3), set up Hugging Face access.** That repository is gated: accept the agreement for [black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy) with the account that owns your token, then add a Hugging Face **read** token to Runpod Secrets as **HUGGINGFACE_TOKEN**. The template maps that secret to `HF_TOKEN`; never paste credentials into public template fields. **FLUX.1 and FLUX.2 are ungated and need no account or token.**
4. Open **Connect → HTTP 8188 / ComfyUI** once the service reports Ready. The template exposes ComfyUI only. If the Connect link returns **HTTP 403**, open a blank tab and paste `https://<pod-id>-8188.proxy.runpod.net` into the address bar; see Troubleshooting.
5. Pick a workflow in the sidebar, edit the prompt and settings, and click Queue. Save generated images before deleting or replacing the Pod.

Storage is temporary. The template attaches no network volume. First-boot downloads resume, your workflow edits persist across restarts, and no model weights or credentials are baked into the image.

## Simple workflows

**FLUX.2 (`:2`, the default):**

- **01 Dev Text to Image** and **02 Dev Image to Image:** FLUX.2 dev, 1280 × 720.
- **11–13 Turbo (Klein 4B):** text-to-image and image-to-image on the smaller model, for 48 GB cards. Installed alongside dev when `MODEL_MODE=both`.
- Image-to-image: upload a picture and describe the change.

The sections below describe the FLUX 3 Klein (`:3`) workflows and node.

**FLUX 3 (`:3`):**

- **01 Distilled Text to Image:** 15 steps, cfg 1.0, er_sde/simple, 1280 × 720.
- **02 Base Text to Image:** the undistilled checkpoint on the same reference settings — 15 steps, cfg 1.0, er_sde/simple, 1280 × 720.
- **03–04 Image Edit:** upload a picture and describe the changes; uses the same base or distilled checkpoint as generation.
- **10–13 Advanced:** editable upstream ComfyUI graphs for text generation and reference-image editing. Upload your own image for editing; example asset names are placeholders.

The simple node exposes prompt, negative prompt, mode, dimensions, seed, steps, guidance, sampler, schedule, prompt upsampling and its token budget. Canvas defaults to **1280 × 720**.

**Guidance.** Both official FLUX 3 Klein graphs — base and distilled — sample at **cfg 1.0** with 15 `er_sde`/`simple` steps. The model is guidance-distilled, so classifier-free guidance is not how it is steered, and raising cfg between about 1.5 and 4 changes the image very little while making ComfyUI run a second forward pass per step. The packaged defaults match the reference graphs. Earlier releases ran base at 50 steps and cfg 3.5, roughly seven times the compute for no benefit.

**Negative prompt.** A broad general-purpose negative prompt is filled in, covering optical defects, exposure and colour faults, anatomy errors, framing mistakes, and overlays such as watermarks and captions. It is passed **only when guidance is above 1.0**, and the reference configuration is cfg 1.0, so at the defaults it is inert — there is no unconditional branch for it to steer. Raise guidance above 1.0 to make it take effect, at the cost of a second forward pass per step. The field is kept because it is the only way to use a negative at all, not because the defaults use one.

**Prompt expansion** runs locally through the pinned Qwen3.5 9B upsampler and is **off by default**, which departs from the reference graphs deliberately. Black Forest Labs state that the model relies on it and that raw, short prompts without it give poor adherence and distorted output, so turn it on when adherence matters. It is a second large model — 9.75 GB resident alongside the transformer and text encoder — and the three compete on a 48 GB card, so ComfyUI swaps between the expansion pass and sampling and the cost lands on every image. Leave it off for fast iteration with prompts you have written out in detail.

**Prompt wording matters more than parameters.** The Qwen text encoder attaches adjectives the way a reader would: "dark brunette woman" binds *dark* to the person, and can yield very dark skin, while "dark-haired brunette" binds it to the hair. Say which noun each adjective modifies.

The advanced graphs preserve the official template structure, with the upsampler filename changed from W4A8 to the downloaded INT8 checkpoint. Original system prompt and graph sources: [Comfy-Org templates](https://github.com/Comfy-Org/workflow_templates/tree/abb9cf6477b59c52dbe234c67f82318dadd872b2/templates), [BFL ComfyUI model card](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy).

## Image editing and model reuse

The simple FLUX node also has an optional reference-image socket. Connect an uploaded image to enable instruction-based editing; disconnect it for text-to-image. The image is encoded with the same VAE and attached as native reference conditioning. The local prompt upsampler sees the image when connected. Loader identities and filenames are shared across paired workflows so ComfyUI can reuse cached models. Switching between base and distilled selects different checkpoints.

## Seeds

The seed widget carries ComfyUI's standard **control after generate** control, set to `randomize` in every packaged workflow, so each run uses a new seed. Set it to `fixed` to reproduce an exact image, or `increment` to walk a series. Earlier releases pinned the seed at 42 with the control disabled, which made every run of a workflow produce the same picture.

## Image preview ribbon

A strip of recent output images sits along the bottom of the ComfyUI window and refreshes as each queued graph finishes, so you can queue a long batch and watch it fill.

Click any thumbnail to open the viewer. **Left and right arrow keys** move through the batch, **space** picks the current image, **D** downloads it and **Escape** closes. The tick in the corner of a thumbnail picks it without opening the viewer. **Download picked** then saves just those files, which is the point: queue fifty, skim them, keep the three that worked.

Picks live for the session and are never uploaded. The ribbon reads the recent `/history` entries through ComfyUI's own `/view` endpoint, skips transient previews, and never scans the output directory.

## Environment variables

- `HF_TOKEN`: Hugging Face read credential, mapped to `{{ RUNPOD_SECRET_HUGGINGFACE_TOKEN }}`. **Required only for `:3` (FLUX 3)**, whose repository is gated and must be accepted by the same account. FLUX.1 and FLUX.2 download anonymously, so the default `:2` Pod needs no token.
- `HF_HOME=/workspace/.cache/huggingface`: Hugging Face cache/metadata location.
- `MODEL_MODE=dev`: which variant to download — `dev`, `turbo` (Klein 4B) or `both`. `base` or `distilled` limits first-boot downloads. Both variants share the pinned text encoders, prompt upsampler and VAE, so neither choice skips those components.
- `STUDIO_VERSION=2`: which generation this image serves, baked at build time from the matching `versions/<n>/profile.json`. It selects the weights downloaded on first boot and the workflows installed. Pull the `:1` or `:3` tag for another generation rather than changing this on a running Pod.
- `PORT=8000`: gateway HTTP port used by the Runpod Hub/Serverless listing. The Pod template does not expose it; Pod users reach ComfyUI directly on 8188.
- `PORT_HEALTH=8001`: readiness service used by the Hub listing; `/ping` returns 503 until ComfyUI responds with device information. Not exposed by the Pod template.
- `OMP_NUM_THREADS=8`, `MKL_NUM_THREADS=8`: runtime CPU-thread defaults; override to match the Pod's allocated CPU quota.
- `PUBLIC_KEY`: optional SSH public key for diagnostics. When present, the container starts SSH on port 2222; the template does not expose this port. The disposable Actions test exposes it only for its ephemeral key.

`RUNPOD_API_KEY` and `GITHUB_PACKAGES_PAT` are local deployment credentials only; never pass them into the worker container. GitHub Actions uses repository secrets for Runpod validation. The account's existing GHCR registry authorization is supplied separately to disposable test Pods where required.

## Build, validate and update

All container builds and runtime tests run in **GitHub Actions**. Do not build on the local workstation. Push to `develop` or `main`, or dispatch the build workflow. Paid GPU tests are opt-in through the `gpu_smoke` dispatch input; ordinary pushes build and run CPU checks only. The workflow runs source checks, builds on an Actions runner, starts a CPU-only ComfyUI service inside the build to verify graph schemas, then publishes the image. When dispatched with `gpu_smoke=true`, it launches a disposable 48 GB L40S Pod using that exact image digest (override with `VALIDATION_GPU_TYPES`) and generates a 512×512 image and an image-edit result with each checkpoint, grouping each pair to keep that model loaded. Validation checks dimensions, pixel variance and entropy; these detect blank outputs, not artistic quality. PNGs, system metadata and results are uploaded as Actions artifacts. A `finally` block and an unconditional cleanup step delete the test Pod.

The package must be public on GHCR for anonymous template users; account registry credentials can support private validation. Configure Actions secrets `RUNPOD_API_KEY` and, if needed, `RUNPOD_REGISTRY_AUTH_ID`. The `.runpod` listing uses the same image build and environment defaults; its required readiness test does not replace the GPU generation tests. For Serverless browser use, keep exactly one active worker and supply Runpod authentication on HTTP and WebSocket requests. The Pod template is the straightforward browser deployment.

Build and GPU-validation status must be confirmed in Actions before treating a revision as tested. Captured package versions are stored in `/opt/acdev/python-lock.txt` inside each image. To update a model generation, add a new version profile, regenerate its workflow defaults and manifests, update the corresponding container tags, and repeat the remote tests. No runtime dependency upgrades or branch-head model downloads occur during Pod startup.

## Troubleshooting

- **Connect opens ComfyUI with HTTP 403:** ComfyUI's browser-origin guard rejects cross-site page navigations, and a link clicked from the Runpod dashboard or any other site counts as cross-site. This image patches the guard at build time to permit only a safe top-level `GET /` navigation; cross-site API, WebSocket, form and subresource requests stay blocked. On a Pod built from an older digest, open a blank tab and paste `https://<pod-id>-8188.proxy.runpod.net` into the address bar, which the browser sends as a same-origin navigation.
- **Connect shows ERR_INVALID_RESPONSE:** the same 403, returned with a body the browser cannot render. Treat it as the entry above.
- **ComfyUI does not become ready:** first boot downloads the pinned weights before ComfyUI starts. Check the Pod logs; the service answers only after it reports device information.
- **Out of GPU memory:** FLUX.2 `dev` needs an 80 GB card; on a 48 GB card set `MODEL_MODE=turbo` to run Klein 4B. A 24 GB card cannot hold any variant.

## CPU thread sizing

CPU thread pools are sized automatically to the container CPU quota and available CPUs before PyTorch starts, avoiding host-sized pools that can throttle image scaling and export. Set `OMP_NUM_THREADS` and optionally `MKL_NUM_THREADS` to override; startup logs show the selected values. Actual speedup depends on the workload and has not been benchmarked for this revision.

## Editable render size

Set **Render Width** and **Render Height** on the canvas, or **Width** and **Height** in the main controls panel. These fields drive generation directly; resolution presets no longer override them. The added image-resize controls use a center crop to the selected dimensions; change the resize node’s crop setting if needed. Use dimensions supported by the model (multiples of 32 for LTX video, 16 for image workflows). LTX’s two-stage workflows retain their internal half-resolution first pass and upscale to the selected output size. Existing installed workflows and user edits are preserved; open a newly packaged workflow to get these controls.
