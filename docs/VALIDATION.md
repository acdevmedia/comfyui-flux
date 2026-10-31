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

## FLUX.2 (`:2`) — GPU generation

Both variants were run from image digest `sha256:ec1ecfdca9375c2b6ac1b8fadc2320b23c790c11628f974837ea06ec05c1e874`
(commit `0c1ed5b`) on disposable Pods that downloaded only the weights for the variant under test and were deleted
automatically. Everything ran at the **upstream templates' own settings**, shrunk to 512 × 512 for cost with the seed
pinned to 42. The graphs are Comfy-Org's templates flattened by a real ComfyUI frontend, so they are what the
sidebar workflows execute.

| Variant | Card | Workflow | Elapsed | Entropy |
| --- | --- | --- | --- | --- |
| Klein (turbo) | A40 48 GB, $0.59/hr | 11 Klein Text to Image | 22.69 s | 8.86 |
| Klein (turbo) | A40 48 GB | 12 Klein Base Image to Image | 11.87 s | 9.24 |
| Klein (turbo) | A40 48 GB | 13 Klein Image to Image | 12.00 s | 8.74 |
| dev | A100 80 GB, $1.79/hr | 01 Dev Text to Image | 40.06 s | 9.20 |
| dev | A100 80 GB | 02 Dev Image to Image | 32.27 s | 9.23 |

The PNGs were inspected rather than trusted to the numeric checks.

- **Klein text to image:** a hedgehog in a party hat on a confetti-covered floor in a flash-photo style, with correct
  anatomy and sharp detail.
- **Klein edits:** "Change the background to a cozy, softly lit interior" turned the dark background into a bright
  living room with curtains, a window and a sofa, changing about 87% of the pixels, while the hedgehog, hat and
  confetti survived. This is a large whole-background edit working at the template defaults. "Change the bag color to
  blue" was applied to a picture that has no bag, and the model changed the hat to blue instead, altering about 2.8%.
- **dev text to image:** a fashion photograph of a woman in an embroidered gown against pastel brutalist architecture,
  with convincing fabric detail and clean edges.

### The dev edit result proves little

The dev image-to-image template's instruction is "Apply the design from Reference Image 1 onto objects in Reference
Image 2", a **two-reference** graph. The harness uploaded the same picture into both reference slots, so there was
nothing to transfer and the output was nearly identical to the input (mean difference 3.6 of 255, no pixel changed by
more than 40). That is the correct answer to that input, and it passed the harness's weak "differs from the source"
check, but **it does not show that dev edits well**. The harness now gives each later reference slot a distinct
picture. The dev edit has not been re-run with it.

## Not validated (FLUX.2)

- **The 1280 × 720 default.** The two text-to-image workflows now default to 1280 × 720, as requested, but every run
  above was 512 × 512, so that size has not been rendered.
- **Dev image-to-image** with two genuinely different references, as above.
- **Other cards.** Klein ran only on an A40 and dev only on an A100 80 GB.
- **The Turbo LoRA switch on dev.** The dev templates include a toggle for the Turbo LoRA; the runs used its default
  and no other position was tried.
- **Content filtering.** One prompt per workflow, which says nothing about borderline prompts.

## Not yet validated (FLUX 3 and FLUX.1)

The ComfyUI origin-guard patch is applied during the image build, and the build fails if the pinned `server.py` guard does not match exactly once, so the patched code is present in the published image. Its runtime effect has not been confirmed against a live Pod: no cross-site navigation has been sent to a Pod running this digest. The ComfyUI-only port layout is exercised by the run above, which provisioned with `8188/http` only and reached readiness through ComfyUI directly.

## Harness notes

Remote validation is opt-in through the `gpu_smoke` dispatch input; ordinary pushes build and run CPU checks only. `scripts/test-runpod.py --keep` leaves the Pod running for manual inspection, `--pod <id>` re-runs the matrix against a running Pod, and `--cleanup` deletes it. Pod reuse randomises seeds, because ComfyUI returns cached outputs in milliseconds for an identical prompt and seed, which would otherwise look like a passing run that never executed.
