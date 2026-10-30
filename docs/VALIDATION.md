# Validation status — FLUX 3 Image Klein

## Container

Commit `e3bdce8` built and published in [GitHub Actions](https://github.com/acdevmedia/comfyui-flux/actions). Published digest: `sha256:bd9e5f5c72f4bf3d1e0c12382f3d7c9c0045a3846695676b94d7c3664d9b87c6`. Source checks, pinned model metadata, graph schemas and Dockerfile parity passed.

## GPU generation — NVIDIA L40S 48 GB

All four packaged graphs executed on a disposable L40S Pod (`$1.09/hr`) from the digest above. Times are ComfyUI's own recorded execution durations, read from the Pod's `/history`:

| Workflow | Execution | Result |
| --- | --- | --- |
| 02 Base Text to Image | 80.86 s | 512 × 512, entropy 8.30 |
| 04 Base Image Edit | 55.28 s | 512 × 512, entropy 8.76, differs from source |
| 01 Distilled Text to Image | 5.79 s | 512 × 512, entropy 9.11 |
| 03 Distilled Image Edit | 21.85 s | 512 × 512, entropy 9.29 |

Checks cover dimensions, pixel variance and entropy, and for edits that the output differs from the uploaded source. They detect blank, uniform or passthrough output; they do not judge artistic quality or prompt adherence. Each variant's generate/edit pair ran together so the checkpoint stayed loaded, confirming generation and editing share one loaded model.

An earlier A100 80 GB run of the same package measured base text-to-image at 94.51 s and 30.66 s across two runs. The L40S is not meaningfully slower for this workload and costs less, so it is the documented default. Peak residency is about 21 GB; a 24 GB card is not sufficient once the prompt upsampler is resident.

## Not yet validated

The ComfyUI origin-guard patch and the ComfyUI-only port layout landed after the digest above was built. They are verified by source tests and by patching a copy of the pinned `server.py`, but no Pod has yet been launched from an image containing them. Re-run the `gpu_smoke` dispatch against the next published digest before treating the 403 fix as confirmed in deployment.

## Harness notes

Remote validation is opt-in through the `gpu_smoke` dispatch input; ordinary pushes build and run CPU checks only. `scripts/test-runpod.py --keep` leaves the Pod running for manual inspection, `--pod <id>` re-runs the matrix against a running Pod, and `--cleanup` deletes it. Pod reuse randomises seeds, because ComfyUI returns cached outputs in milliseconds for an identical prompt and seed, which would otherwise look like a passing run that never executed.
