# Runpod deployment

Use the repository [README](../README.md) for the FLUX 3 setup. Publish `ghcr.io/acdevmedia/flux-comfyui:3` through GitHub Actions, then run `python3 scripts/create-runpod-template.py` to create or update the FLUX template. Use `--dry-run` to review its payload. The script matches the single account template by name; the Eros, Sulphur and Ideogram templates are not touched.
