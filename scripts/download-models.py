"""Pinned, resumable first-boot model downloads. No model weights in the image."""
import hashlib,json,os,shutil,sys
from pathlib import Path
from huggingface_hub import hf_hub_download,snapshot_download
version=os.getenv('STUDIO_VERSION','3')
p=json.loads(Path('/opt/acdev/versions/%s/profile.json'%version).read_text())
mode=os.getenv('MODEL_MODE','both')
# A variant need not own a file (Qwen's standard mode is the base model without the LoRA), so the
# profile may declare its variants outright; otherwise infer them from the tagged models.
variants=list(p.get('variants') or sorted({m.get('variant') for m in p['models']+p.get('snapshots',[]) if m.get('variant')}))
allowed=variants+['both'] if variants else ['both']
if mode not in allowed:raise SystemExit('MODEL_MODE for generation %s must be one of: %s'%(version,', '.join(allowed)))
token=os.getenv('HF_TOKEN','').strip()
if token.startswith(('{{','YOUR_')):token=''
# Z-Image's weights are ungated, so a token is optional; it is still honoured when supplied.
if p.get('gated') and not token:raise SystemExit('This generation needs HF_TOKEN from Runpod Secret HUGGINGFACE_TOKEN, with each gate accepted by that account.')
token=token or None
root=Path('/workspace/ComfyUI/models');root.mkdir(parents=True,exist_ok=True)
for m in p['models']:
 variant=m.get('variant')
 if mode!='both' and variant and variant!=mode:continue
 dest=root/m['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
 marker=dest.with_suffix('.verified.json');expected={'sha256':m['sha256'],'size':m['size']}
 if dest.exists() and dest.stat().st_size==m['size'] and marker.exists() and json.loads(marker.read_text())==expected:continue
 if shutil.disk_usage(root).free<m['size']+10*10**9:raise SystemExit('Insufficient storage: use a 200 GB container disk.')
 print('[models] Downloading/verifying',m['file'],flush=True)
 path=Path(hf_hub_download(m['repo'],m['file'],revision=m['revision'],token=token,local_dir=root))
 digest=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(16*1024*1024),b''):digest.update(chunk)
 if path.stat().st_size!=m['size'] or digest.hexdigest()!=m['sha256']:raise SystemExit('Model checksum mismatch: '+m['file'])
 if path!=dest:shutil.move(path,dest)
 marker.write_text(json.dumps(expected))
for m in p.get('snapshots',[]):
 if mode=='base' and m['directory']=='distilled':continue
 dest=root/'ideogram'/m['directory'];dest.mkdir(parents=True,exist_ok=True)
 print('[models] Preparing',m['repo'],'at pinned revision',m['revision'],flush=True)
 snapshot_download(m['repo'],revision=m['revision'],token=token,local_dir=dest,
                   ignore_patterns=['transformer/*','unconditional_transformer/*'] if mode=='distilled' and m['directory']=='base' else None,
                   allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken','tokenizer/*','scheduler/*','text_encoder/*','vae/*','transformer/*','unconditional_transformer/*','prompt_enhancer_head/*'],max_workers=4)
print('[models] Required downloads complete; starting ComfyUI.',flush=True)
