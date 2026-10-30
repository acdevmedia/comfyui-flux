"""Simple FLUX 3 controls expanding to native, inspectable ComfyUI nodes."""
from pathlib import Path
from comfy_execution.graph_utils import GraphBuilder


class FluxStudio:
    CATEGORY = 'ACDEV/FLUX 3'
    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('image', 'expanded_prompt')
    FUNCTION = 'generate'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'prompt': ('STRING', {'multiline': True, 'default': 'A fox reading a newspaper in a sunny Paris cafe, editorial illustration, warm colors.'}),
            # Only applied when guidance > 1.0; the distilled path runs without an effective CFG branch.
            'negative_prompt': ('STRING', {'multiline': True, 'default': 'blurry, out of focus, motion blur, lowres, pixelated, jpeg artifacts, compression artifacts, banding, moire, chromatic aberration, heavy grain, oversharpened, overexposed, blown highlights, underexposed, crushed blacks, washed out, oversaturated, bad anatomy, deformed, disfigured, mutated, extra limbs, extra fingers, missing fingers, fused fingers, malformed hands, poorly drawn face, asymmetric eyes, bad proportions, cropped head, cut off, out of frame, duplicate, cloned face, watermark, signature, logo, copyright notice, username, timestamp, stock photo caption, subtitles, ui overlay, hud, border, frame, letterbox, amateur, sloppy, unfinished, placeholder, error message'}),
            'mode': (['distilled', 'base'],),
            'width': ('INT', {'default': 1280, 'min': 256, 'max': 2048, 'step': 16}),
            'height': ('INT', {'default': 720, 'min': 256, 'max': 2048, 'step': 16}),
            'seed': ('INT', {'default': 0, 'min': 0, 'max': 2**63-1, 'control_after_generate': True}),
            'steps': ('INT', {'default': 15, 'min': 1, 'max': 100}),
            # FLUX 3 Klein is guidance-distilled: the reference graphs sample at cfg 1.0 for both
            # variants. Above 1.0 ComfyUI runs true CFG, doubling the forward passes per step.
            'guidance': ('FLOAT', {'default': 1.0, 'min': 1.0, 'max': 10.0, 'step': 0.1}),
            'sampler': (['er_sde', 'euler', 'heun'],),
            'scheduler': (['simple', 'normal', 'beta'],),
            'upsample_prompt': ('BOOLEAN', {'default': True}),
            'max_prompt_tokens': ('INT', {'default': 1024, 'min': 128, 'max': 4096}),
        }, 'optional': {'reference_image': ('IMAGE', {'rawLink': True})}}

    def generate(self, prompt, negative_prompt, mode, width, height, seed, steps, guidance, sampler, scheduler,
                 upsample_prompt, max_prompt_tokens, reference_image=None):
        graph = GraphBuilder()
        expanded = prompt
        if upsample_prompt:
            upsampler = graph.node('CLIPLoader', clip_name='qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors', type='flux3', device='default')
            params = {'clip': upsampler.out(0), 'prompt': prompt, 'max_length': max_prompt_tokens,
                      'sampling_mode': 'on', 'sampling_mode.temperature': 1.0,
                      'sampling_mode.top_k': 1, 'sampling_mode.top_p': 0.95,
                      'sampling_mode.min_p': 0.0, 'sampling_mode.repetition_penalty': 1.05,
                      'sampling_mode.seed': seed, 'sampling_mode.presence_penalty': 1.5,
                      'thinking': False, 'use_default_template': True, 'mtp': 'off',
                      'system_prompt': Path('/opt/acdev/config/flux-system-prompt.txt').read_text()}
            if reference_image is not None:
                params['image'] = reference_image
                params['system_prompt'] = 'Expand this image-editing request into a detailed instruction. Describe only the requested changes, preserve everything else, and refer to the uploaded picture as <ref_image_0>.'
            expanded = graph.node('TextGenerate', **params).out(0)
        model_name = 'flux3-image-klein-base-int8-convrot.safetensors' if mode == 'base' else 'flux3-image-klein-int8-convrot.safetensors'
        model = graph.node('UNETLoader', unet_name=model_name, weight_dtype='default')
        clip = graph.node('CLIPLoader', clip_name='qwen3vl_4b_int8_convrot.safetensors', type='flux3', device='default')
        positive = graph.node('CLIPTextEncode', clip=clip.out(0), text=expanded)
        negative = graph.node('CLIPTextEncode', clip=clip.out(0), text=negative_prompt if guidance > 1.0 else '')
        vae = graph.node('VAELoader', vae_name='flux2-vae.safetensors')
        if reference_image is not None:
            reference = graph.node('VAEEncode', pixels=reference_image, vae=vae.out(0))
            positive = graph.node('ReferenceLatent', conditioning=positive.out(0), latent=reference.out(0))
            negative = graph.node('ReferenceLatent', conditioning=negative.out(0), latent=reference.out(0))
        latent = graph.node('EmptyFlux2LatentImage', width=width, height=height, batch_size=1)
        samples = graph.node('KSampler', model=model.out(0), positive=positive.out(0), negative=negative.out(0),
                             latent_image=latent.out(0), seed=seed, steps=steps, cfg=guidance,
                             sampler_name=sampler, scheduler=scheduler, denoise=1.0)
        image = graph.node('VAEDecode', samples=samples.out(0), vae=vae.out(0))
        return {'result': (image.out(0), expanded), 'expand': graph.finalize()}


NODE_CLASS_MAPPINGS = {'AcdevFluxStudio': FluxStudio}
NODE_DISPLAY_NAME_MAPPINGS = {'AcdevFluxStudio': 'FLUX 3 — Prompt and shot settings'}
