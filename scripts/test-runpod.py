"""Actions-only disposable GPU test. Always deletes the pod, including on failure."""
import argparse,copy,io,json,os,random,signal,subprocess,time,urllib.parse,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.runtime';OUT.mkdir(exist_ok=True)
PROFILE=json.loads((ROOT/'config/profile.json').read_text())
KEY=os.environ.get('RUNPOD_API_KEY','')
KEEP=False
GPU_TYPES=[g.strip() for g in os.environ.get('VALIDATION_GPU_TYPES','NVIDIA L40S,NVIDIA RTX A6000,NVIDIA A40').split(',') if g.strip()]

def request(url,method='GET',data=None,auth=False,raw=False):
 headers={'User-Agent':'acdev-validation','Content-Type':'application/json'}
 if auth:headers['Authorization']='Bearer '+KEY
 req=urllib.request.Request(url,method=method,data=json.dumps(data).encode() if data is not None else None,headers=headers)
 with urllib.request.urlopen(req,timeout=45) as response:
  data=response.read()
  return data if raw else json.loads(data) if data else None

def cloud(path,method='GET',data=None):return request('https://rest.runpod.io/v1'+path,method,data,auth=True)

def cleanup(force=False):
 state=OUT/'pod.json'
 if not state.exists():return
 if KEEP and not force:
  print('Keeping validation pod for manual testing; delete it with --cleanup',flush=True);return
 pod=json.loads(state.read_text())
 if pod.get('deleted'):return
 try:cloud('/pods/'+pod['id'],'DELETE')
 except urllib.error.HTTPError as exc:
  if exc.code!=404:raise
 pod['deleted']=True;state.write_text(json.dumps(pod,indent=2))
 print('Deleted validation pod',pod['id'],flush=True)

def logs(pod_id):
 try:
  pod=cloud('/pods/'+pod_id);ip=pod.get('publicIp');port=pod.get('portMappings',{}).get('2222')
  if ip and port:
   result=subprocess.run(['ssh','-i',str(OUT/'test-key'),'-p',str(port),'-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(OUT/'known_hosts'),'-o','ConnectTimeout=10','root@'+ip,'tail -n 180 /workspace/logs/studio-startup.log'],capture_output=True,text=True,timeout=30)
   (OUT/'startup.log').write_text(result.stdout+result.stderr)
 except Exception as exc:print('Diagnostic retrieval:',type(exc).__name__,flush=True)

def graph_mode(path,graph):
 """Variant label: the Studio node's mode input if there is one, else the filename token."""
 for n in graph.values():
  if n['class_type'].endswith('Studio') and 'mode' in n['inputs']:return str(n['inputs']['mode'])
 parts=path.stem.split('_')
 return parts[1] if len(parts)>1 else 'default'

def is_edit(graph):return any(n['class_type']=='LoadImage' for n in graph.values())

def apply_test_settings(graph,reuse):
 """Shrink to 512 and fix the seed so runs are comparable; randomise only when reusing a Pod."""
 for n in graph.values():
  c,i=n['class_type'],n['inputs']
  if c.endswith('Studio'):i.update(width=512,height=512)
  if c in ('EmptySD3LatentImage','EmptyFlux2LatentImage','EmptyLatentImage'):i.update(width=512,height=512)
  if c=='ImageScaleToTotalPixels':i['megapixels']=0.25
  # A fixed seed keeps runs comparable; a reused Pod needs a fresh one to defeat ComfyUI's cache.
  seed=random.randrange(1,2**31) if reuse else 42
  for key in ('seed','noise_seed'):
   if key in i and not isinstance(i[key],list):i[key]=seed
  if c=='SaveImage':i['filename_prefix']='validation/'+graph_label[0]

def synthetic_source(index=0):
 """A structured 512x512 picture for edit-only graphs, which have nothing to generate one from."""
 from PIL import Image,ImageDraw
 img=Image.new('RGB',(512,512));px=img.load()
 for y in range(512):
  for x in range(512):
   r,g,b=(40+x//4,60+y//5,150-x//6)
   px[x,y]=((r,g,b),(b,r,g),(g,b,r))[index%3]   # a different palette per reference slot
 d=ImageDraw.Draw(img)
 d.ellipse((150,120,360,330),fill=(224,172,105),outline=(30,20,10),width=4)
 d.rectangle((60,380,450,470),fill=(190,60,50),outline=(255,255,255),width=3)
 buf=io.BytesIO();img.save(buf,'PNG');return buf.getvalue()

def upload_image(base,data,filename):
 boundary='acdev-validation-upload'
 body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
 req=urllib.request.Request(base+'/upload/image',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary,'User-Agent':'acdev-validation'})
 with urllib.request.urlopen(req,timeout=45) as response:return json.load(response)['name']

def judge(raw,edit,source):
 """Reject blank, flat and passthrough frames. Texture-heavy corruption still needs a human eye."""
 from PIL import Image,ImageStat,ImageChops
 image=Image.open(io.BytesIO(raw)).convert('RGB');m=ImageStat.Stat(image)
 if edit:assert abs(image.size[0]-512)<=32 and abs(image.size[1]-512)<=32,image.size
 else:assert image.size==(512,512),image.size
 assert max(m.stddev)>8,'Output is blank or nearly uniform'
 assert image.entropy()>3,'Output lacks image detail'
 flat=image.resize((128,128)).quantize(colors=16).convert('RGB')
 dominant=max(c for c,_ in flat.getcolors(4096))/(128*128)
 if (image.entropy()<5.5 and max(m.stddev)<40) or dominant>0.75:
  raise AssertionError('Output looks like a flat frame or refusal card (entropy %.2f, stddev %.1f, %.0f%% one colour)'%(image.entropy(),max(m.stddev),dominant*100))
 if edit:
  diff=ImageStat.Stat(ImageChops.difference(source.resize(image.size),image))
  assert max(diff.mean)>0.5,'Editing returned the unchanged source image'
 return image,m

graph_label=['']

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--cleanup',action='store_true');parser.add_argument('--keep',action='store_true');parser.add_argument('--pod',default='');args=parser.parse_args()
 global KEEP
 KEEP=args.keep
 if args.cleanup:cleanup(force=True);return
 assert KEY,'RUNPOD_API_KEY Actions secret is required'
 digest=os.environ.get('IMAGE_DIGEST','')
 assert args.pod or digest.startswith('sha256:'),'IMAGE_DIGEST is required unless --pod reuses a running pod'
 if args.pod:KEEP=True
 for suffix in ('','.pub'):(OUT/('test-key'+suffix)).unlink(missing_ok=True)
 subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(OUT/'test-key')],stdin=subprocess.DEVNULL,check=True)
 config=json.loads((ROOT/'config/runpod-template.json').read_text());env={**config['env'],'PUBLIC_KEY':(OUT/'test-key.pub').read_text().strip()}
 # The matrix executes every packaged graph, so the Pod needs every variant's weights.
 env['MODEL_MODE']=os.environ.get('VALIDATION_MODEL_MODE','both')
 payload={'name':f'acdev-{PROFILE["kind"]}-{os.environ.get("GITHUB_RUN_ID","test")}-validation','imageName':config['imageName'].split(':')[0]+'@'+digest,'cloudType':'SECURE','computeType':'GPU','gpuTypeIds':GPU_TYPES,'gpuTypePriority':'availability','gpuCount':1,'containerDiskInGb':200,'volumeInGb':0,'volumeMountPath':'/workspace','ports':['8188/http','2222/tcp'],'supportPublicIp':True,'env':env}
 if os.environ.get('RUNPOD_REGISTRY_AUTH_ID'):payload['containerRegistryAuthId']=os.environ['RUNPOD_REGISTRY_AUTH_ID']
 def deadline(signum, frame):raise TimeoutError('Validation deadline reached; deleting test pod')
 signal.signal(signal.SIGALRM, deadline)
 signal.signal(signal.SIGTERM, deadline)
 signal.alarm(int(os.environ.get('VALIDATION_DEADLINE_MINUTES','45')) * 60)
 pod={'id':args.pod} if args.pod else None
 if not args.pod:
  existing=[x for x in cloud('/pods') if x.get('name')==payload['name']]
  assert not existing,'A validation pod named %s already exists (%s); delete it before starting another.'%(payload['name'],', '.join(x['id'] for x in existing))
 try:
  if args.pod:print('Reusing running validation pod:',args.pod,flush=True)
  else:pod=cloud('/pods','POST',payload)
  if not args.pod:
   (OUT/'pod.json').write_text(json.dumps({'id':pod['id'],'created_at':time.time(),'image':payload['imageName'],'costPerHr':pod.get('costPerHr')},indent=2))
   print('Validation pod:',pod['id'],'hourly rate:',pod.get('costPerHr'),flush=True)
  base=f'https://{pod["id"]}-8188.proxy.runpod.net';start=time.monotonic()
  while time.monotonic()-start<1800:
   try:
    if request(base+'/system_stats').get('devices'):break
   except Exception:pass
   status=cloud('/pods/'+pod['id'])
   if status.get('desiredStatus') in ['EXITED','TERMINATED']:raise RuntimeError('Validation pod exited before readiness')
   print('Waiting for image pull/model provisioning:',round(time.monotonic()-start),'seconds',flush=True);time.sleep(20)
  else:raise TimeoutError('Pod did not become ready in 30 minutes')
  stats=request(base+'/system_stats');assert any(d.get('type')=='cuda' for d in stats['devices']),stats
  (OUT/'system.json').write_text(json.dumps(stats,indent=2))
  info=request(base+'/object_info');results={};generated={}
  paths=list((ROOT/'versions'/PROFILE['version']/'api').glob('*.json'))
  assert paths,'Generation %s packages no API graphs, so there is nothing to validate; '\
    'add them before running a paid GPU test against it.'%PROFILE['version']
  only=os.environ.get('VALIDATION_ONLY','').strip().upper()
  if only:   # test one variant's graphs, so a Pod only needs that variant's weights
   paths=[p for p in paths if only in p.name.upper()]
   assert paths,'VALIDATION_ONLY=%s matches no packaged graph'%only
  loaded={p:json.loads(p.read_text()) for p in paths}
  # Generate before editing within a variant, so an edit can start from the model's own output.
  for path in sorted(paths,key=lambda q:(graph_mode(q,loaded[q]),is_edit(loaded[q]),q.name)):
   graph=loaded[path];mode=graph_mode(path,graph);edit=is_edit(graph);graph_label[0]=path.stem
   for n in graph.values():assert n['class_type'] in info,'Unknown node type in '+path.name+': '+n['class_type']
   apply_test_settings(graph,bool(args.pod))
   source=None
   if edit:
    from PIL import Image
    source_bytes=generated.get(mode) or synthetic_source()
    source=Image.open(io.BytesIO(source_bytes)).convert('RGB')
    for index,node in enumerate(n for n in graph.values() if n['class_type']=='LoadImage'):
     # Two-reference graphs (a design and a target) are meaningless with the same picture twice, so
     # slots after the first get a distinct synthetic image.
     data=source_bytes if index==0 else synthetic_source(index)
     node['inputs']['image']=upload_image(base,data,f'validation-{mode}-{index+1}.png')
   begin=time.monotonic();queued=request(base+'/prompt','POST',{'prompt':graph});pid=queued['prompt_id']
   while time.monotonic()-begin<900:
    history=request(base+'/history/'+pid)
    if pid in history:
     result=history[pid];assert result['status']['status_str']=='success',result['status']
     images=[im for output in result.get('outputs',{}).values() for im in output.get('images',[])]
     assert images,'No image was produced'
     raw=request(base+'/view?'+urllib.parse.urlencode(images[0]),raw=True)
     (OUT/(path.stem+'.png')).write_bytes(raw)
     image,metrics=judge(raw,edit,source)
     if not edit:generated[mode]=raw
     results[path.stem]={'seconds':round(time.monotonic()-begin,2),'size':list(image.size),'stddev':metrics.stddev,'entropy':image.entropy(),'status':'passed'}
     print('PASS GPU generation:',path.name,results[path.stem],flush=True);break
    time.sleep(10)
   else:raise TimeoutError('Generation timed out: '+path.name)
  (OUT/'validation.json').write_text(json.dumps({'kind':PROFILE['kind'],'version':PROFILE['version'],'image_digest':digest,'results':results},indent=2))
 finally:
  if pod:
   logs(pod['id']);cleanup()

if __name__=='__main__':main()
