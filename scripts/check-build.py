"""CPU-only container smoke test: boot ComfyUI and validate packaged graph schemas."""
import io,json,subprocess,time,urllib.parse,urllib.request
from pathlib import Path
from PIL import Image
from workflow_dimensions import fit_expression
p=json.loads(Path('/opt/acdev/config/profile.json').read_text())
with open('/tmp/comfy-build-check.log','w') as log:
 proc=subprocess.Popen(['python3','main.py','--cpu','--listen','127.0.0.1','--port','18188'],cwd='/opt/acdev/ComfyUI',stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(180):
   if proc.poll() is not None:raise RuntimeError('ComfyUI exited during CPU smoke check')
   try:
    with urllib.request.urlopen('http://127.0.0.1:18188/object_info',timeout=3) as response:info=json.load(response)
    break
   except Exception:time.sleep(1)
  else:raise TimeoutError('ComfyUI CPU smoke check timed out')
  from verify_frontend import verify_frontend
  verify_frontend()
  for path in (Path('/opt/acdev/versions')/p['version']/'api').glob('*.json'):
   graph=json.loads(path.read_text())
   for node in graph.values():
    assert node['class_type'] in info,(path,node['class_type'])
    schema=info[node['class_type']]['input']
    for key in schema.get('required',{}):assert key in node['inputs'] or any(i.startswith(key+'.') for i in node['inputs']),(path,key)
   print('PASS graph schema:',path.name,flush=True)
  # Run the fit on the pinned nodes: a portrait at Render 1280x720 must come back whole at 720x1280.
  def fit(mine,other):
   return {'class_type':'ComfyMathExpression','inputs':{'expression':fit_expression(mine,other,16),'values.a':1280,'values.b':720,'values.c':['2',0],'values.d':['2',1]}}
  prompt={'1':{'class_type':'EmptyImage','inputs':{'width':1080,'height':1920,'batch_size':1,'color':0}},
          '2':{'class_type':'GetImageSize','inputs':{'image':['1',0]}},'3':fit('c','d'),'4':fit('d','c'),
          '5':{'class_type':'ImageScale','inputs':{'image':['1',0],'upscale_method':'lanczos','width':['3',1],'height':['4',1],'crop':'disabled'}},
          '6':{'class_type':'PreviewImage','inputs':{'images':['5',0]}}}
  request=urllib.request.Request('http://127.0.0.1:18188/prompt',json.dumps({'prompt':prompt}).encode(),{'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=30) as response:pid=json.load(response)['prompt_id']
  for _ in range(120):
   with urllib.request.urlopen('http://127.0.0.1:18188/history/'+pid,timeout=10) as response:history=json.load(response)
   if pid in history:break
   time.sleep(1)
  else:raise TimeoutError('Fitted frame check timed out')
  assert history[pid]['status']['status_str']=='success',history[pid]['status']
  saved=history[pid]['outputs']['6']['images'][0]
  with urllib.request.urlopen('http://127.0.0.1:18188/view?'+urllib.parse.urlencode(saved),timeout=10) as response:picture=response.read()
  size=Image.open(io.BytesIO(picture)).size
  assert size==(720,1280),size
  print('PASS fitted frame:',size,flush=True)
 finally:
  proc.terminate()
  try:proc.wait(timeout=20)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
  print(Path('/tmp/comfy-build-check.log').read_text())
