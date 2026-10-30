# Validation status — FLUX 3 Image Klein

## Container

Commit `e3bdce8` built and published in [GitHub Actions](https://github.com/acdevmedia/comfyui-flux/actions). Published digest: `sha256:bd9e5f5c72f4bf3d1e0c12382f3d7c9c0045a3846695676b94d7c3664d9b87c6`. Source checks, pinned model metadata, graph schemas and Dockerfile parity passed.

## GPU generation — NVIDIA A40 48 GB (CI, run #4)

All four packaged graphs executed on a disposable A40 Pod (`$0.59/hr`) from digest `sha256:dc39fd673568ff758aeb257c891a2ce222fcc7b3f1a5af41191119bfdbc288d9`, built from the commit that adds the ComfyUI origin-guard patch and the ComfyUI-only port layout:

| Workflow | Elapsed | Result |
| --- | --- | --- |
| 02 Base Text to Image | 185.97 s | 512 × 512, entropy 7.70 |
| 04 Base Image Edit | 131.77 s | 512 × 512, entropy 8.60, differs from source |
| 01 Distilled Text to Image | 141.49 s | 512 × 512, entropy 8.91 |
| 03 Distilled Image Edit | 55.46 s | 512 × 512, entropy 9.28 |

Elapsed times include checkpoint swaps between variants, so they are not per-image generation times. PNGs, `system.json` and `validation.json` are attached to the run as the `flux-3-gpu-validation` artifact. Visual inspection of the base pair confirms a detailed illustration with legible rendered text, and an edit that preserves composition, linework and text while changing the palette.

## GPU generation — NVIDIA L40S 48 GB

The same four graphs ran earlier on an L40S (`$1.09/hr`) from digest `sha256:bd9e5f5c72f4bf3d1e0c12382f3d7c9c0045a3846695676b94d7c3664d9b87c6`, using ComfyUI's own recorded execution durations: base text-to-image 80.86 s, base edit 55.28 s, distilled text-to-image 5.79 s, distilled edit 21.85 s. The L40S is roughly twice as fast as the A40 for this workload at under twice the price.

The validation pod requests L40S, RTX A6000 and A40 with `gpuTypePriority: availability`, so the card varies per run; each record above names the card measured. An A100 80 GB is not required: peak residency is about 21 GB, and a 24 GB card is not sufficient once the prompt upsampler is resident.

## Not yet validated

The ComfyUI origin-guard patch is applied during the image build, and the build fails if the pinned `server.py` guard does not match exactly once, so the patched code is present in the published image. Its runtime effect has not been confirmed against a live Pod: no cross-site navigation has been sent to a Pod running this digest. The ComfyUI-only port layout is exercised by the run above, which provisioned with `8188/http` only and reached readiness through ComfyUI directly.

## Harness notes

Remote validation is opt-in through the `gpu_smoke` dispatch input; ordinary pushes build and run CPU checks only. `scripts/test-runpod.py --keep` leaves the Pod running for manual inspection, `--pod <id>` re-runs the matrix against a running Pod, and `--cleanup` deletes it. Pod reuse randomises seeds, because ComfyUI returns cached outputs in milliseconds for an identical prompt and seed, which would otherwise look like a passing run that never executed.
