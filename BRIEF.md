# FLUX 3 bundle maintenance brief

Build the Runpod ComfyUI bundle for `acdevmedia/comfyui-flux`, publishing `ghcr.io/acdevmedia/flux-comfyui:3`, the `3.0.0` version tag and immutable `sha-<commit>` tags through GitHub Actions. Do not build Docker images locally; this workstation has neither the storage nor the CPU budget.

Use FLUX 3 Image Klein from `black-forest-labs/flux-3-image-klein-comfy` at a pinned revision, keeping both the undistilled base and the distilled checkpoint available from one image. The repository is gated: the Hugging Face account that owns the deployed token must accept its agreement before first boot. Keep the pinned Qwen3.5 9B prompt upsampler and the Qwen3-VL text encoder in the same profile.

All current version assets live under `versions/3/`. Each model generation gets its own profile directory and its own container major tag; rebuilds keep the family tag and always add a new commit tag.

Keep the simple workflows genuinely simple — one node exposing prompt, mode, dimensions, seed, steps, guidance, sampler, schedule and prompt upsampling — while retaining the advanced upstream graphs for users who want full control. Text-to-image and image editing must share the same loaded checkpoint. Do not include credentials, model weights or runtime artifacts in the repository or the image context.

Use source validation locally, image build plus CPU graph-schema checks in Actions, and real Runpod GPU generation before claiming runtime behaviour or output quality. Paid GPU validation is opt-in through the `gpu_smoke` dispatch input. `README.md` and `docs/VALIDATION.md` describe the current deployment state.
