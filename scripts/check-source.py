"""Lightweight checks intended for GitHub Actions, without models or GPU."""
import ast,json,re,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=json.loads((root/'config/profile.json').read_text())
assert len(p['comfyui_commit'])==40
for path in root.rglob('*.py'):
 if '.git' not in path.parts:ast.parse(path.read_text(),filename=str(path))
subprocess.run(['bash','-n',str(root/'scripts/start.sh')],check=True)
for path in root.rglob('*.json'):
 if '.git' not in path.parts:json.loads(path.read_text())
# Every packaged generation, not just the active one.
versions=sorted(d.name for d in (root/'versions').iterdir() if d.is_dir())
assert p['version'] in versions
for v in versions:
 q=json.loads((root/'versions'/v/'profile.json').read_text())
 assert q['version']==v and len(q['comfyui_commit'])==40
 for m in q['models']:assert re.fullmatch(r'[0-9a-f]{64}',m['sha256']) and len(m['revision'])==40 and m['size']>0,(v,m['file'],'sha256 must be 64 lowercase hex characters')
 for m in q.get('snapshots',[]):assert len(m['revision'])==40
 names={m['destination'].split('/')[-1] for m in q['models']}
 for wf in (root/'versions'/v/'workflows').glob('*.json'):
  graph=json.loads(wf.read_text())
  groups=[graph.get('nodes') or []]+[s.get('nodes') or [] for s in (graph.get('definitions') or {}).get('subgraphs',[])]
  for nodes in groups:
   for n in nodes:
    if str(n.get('type','')) in ('Note','MarkdownNote'):continue
    for value in (n.get('widgets_values') or []):
     if isinstance(value,str) and value.endswith('.safetensors'):
      assert value in names,(wf.name,n['type'],'references unpinned weight '+value)
for path in (root/'versions'/p['version']/'api').glob('*.json'):
 graph=json.loads(path.read_text());assert any(n['class_type']=='SaveImage' for n in graph.values())
 for n in graph.values():
  for value in n['inputs'].values():
   if isinstance(value,list) and len(value)==2 and isinstance(value[0],str):assert value[0] in graph
assert (root/'Dockerfile').read_text()==(root/'.runpod/Dockerfile').read_text()
assert 'HF_TOKEN' not in (root/'Dockerfile').read_text()
print('PASS: source syntax, pinned model metadata, graphs and Dockerfile parity')
