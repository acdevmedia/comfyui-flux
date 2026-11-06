"""Check that render dimensions resolve to editable controls and that uploads are kept whole."""
import copy
import importlib.util
import json
import math
import sys
import types
from pathlib import Path
from workflow_dimensions import EXACT, FITTED, LATENTS, RESIZE, apply_dimensions, fit_expression, fit_references, link_parts
ROOT=Path(__file__).resolve().parents[1]

def inspect(data):
    definitions={g['id']:g for g in data.get('definitions',{}).get('subgraphs',[])}
    contexts=[]
    def walk(g,parents):
        contexts.append((g,parents))
        for n in g['nodes']:
            if n['type'] in definitions:walk(definitions[n['type']],parents+[(g,n)])
    walk(data,[])
    def proxy_widget(node,name):
        sub=definitions[node['type']]
        idx=next(i for i,x in enumerate(sub['inputs']) if x['name']==name)
        link=next(link_parts(l) for l in sub['links'] if link_parts(l)[1:3]==[-10,idx])
        inner=next(n for n in sub['nodes'] if n['id']==link[3])
        names=[i['name'] for i in inner['inputs'] if i.get('widget')]
        return inner,names.index(inner['inputs'][link[4]]['name'])
    def widget(node,name):
        if name in node.get('widgets_values_named',{}):return node['widgets_values_named'][name]
        names=[i['name'] for i in node.get('inputs',[]) if i.get('widget')]
        if not node.get('widgets_values') and node.get('properties',{}).get('proxyWidgets'):
            inner,index=proxy_widget(node,name)
            return inner['widgets_values'][index]
        return node['widgets_values'][names.index(name)]
    def resolve(g,parents,node,name,depth=0):
        assert depth<40,'dimension wiring cycle'
        inp=next(i for i in node['inputs'] if i['name']==name)
        if inp.get('link') is None:
            assert g is data,(node['id'],name,'dimension is hidden inside a subgraph')
            assert inp.get('widget'),(node['id'],name,'missing editable widget')
            return node,name,widget(node,name),1
        link=next(link_parts(l) for l in g['links'] if link_parts(l)[0]==inp['link'])
        if link[1]==-10:
            parent,inst=parents[-1]
            return resolve(parent,parents[:-1],inst,g['inputs'][link[2]]['name'],depth+1)
        source=next(n for n in g['nodes'] if n['id']==link[1])
        if source['type']=='PrimitiveInt':
            v=next((i for i in source.get('inputs',[]) if i['name']=='value' and i.get('link') is not None),None)
            if v:return resolve(g,parents,source,'value',depth+1)
            assert g is data,(source['id'],'dimension comes from a hidden primitive')
            return source,'value',source['widgets_values'][0],1
        if source['type']=='GetImageSize':
            image_link=next(link_parts(l) for l in g['links'] if link_parts(l)[0]==source['inputs'][0]['link'])
            resize=next(n for n in g['nodes'] if n['id']==image_link[1])
            assert resize['type']=='ResizeImageMaskNode',resize['type']
            axis='width' if link[2]==0 else 'height'
            return resolve(g,parents,resize,'resize_type.'+axis,depth+1)
        if source['type']=='ComfyMathExpression' and source.get('title','').startswith('Fit Frame'):
            # Render Width and Height set the area; the image fills in the proportions.
            return resolve(g,parents,source,'values.a' if source['title'].endswith('Width') else 'values.b',depth+1)
        if source['type']=='ComfyMathExpression':
            assert source['widgets_values'][0]=='a/2',source['widgets_values']
            control,name,value,factor=resolve(g,parents,source,'values.a',depth+1)
            return control,name,value/2,factor/2
        if source['type']=='Reroute':return resolve(g,parents,source,source['inputs'][0]['name'],depth+1)
        raise AssertionError((source['type'],source.get('title'),'dimension still driven by an automatic node'))
    targets=[]
    for g,parents in contexts:
        for n in g['nodes']:
            if n['type'] in LATENTS or (n['type']=='ImageScale' and n.get('title') in (RESIZE,FITTED)):
                for dim in ('width','height'):
                    control,name,value,factor=resolve(g,parents,n,dim)
                    assert isinstance(value,(int,float)) and value>0,(n['id'],dim,value)
                    targets.append((g,parents,n,dim,control,name,factor))
    # Change the controls, then follow the actual graph links to each render input.
    for g,parents,n,dim,control,name,factor in targets:
        expected=1280 if dim=='width' else 736
        if name=='value':control['widgets_values'][0]=expected
        else:
            names=[i['name'] for i in control['inputs'] if i.get('widget')]
            if not control.get('widgets_values') and control.get('properties',{}).get('proxyWidgets'):
                inner,index=proxy_widget(control,name);inner['widgets_values'][index]=expected
            else:control['widgets_values'][names.index(name)]=expected
            if name in control.get('widgets_values_named',{}):control['widgets_values_named'][name]=expected
        assert resolve(g,parents,n,dim)[2]==expected*factor
    return len(targets)

def fitted(step, width, height, image_width, image_height):
    names=dict(a=width,b=height,c=image_width,d=image_height,max=max,round=round,sqrt=math.sqrt)
    return tuple(eval(fit_expression(*sides,step),{'__builtins__':{}},names) for sides in (('c','d'),('d','c')))

# The render area stays put while the image sets the proportions, so a portrait is never sliced.
assert fitted(16,1280,720,1280,720)==(1280,720)
assert fitted(16,1280,720,1920,1080)==(1280,720)
assert fitted(16,1280,720,1080,1920)==(720,1280)
assert fitted(16,1280,720,3000,3000)==(960,960)
assert fitted(16,1024,1024,1024,1536)==(832,1248)
assert all(side%16==0 for side in fitted(16,1280,720,1234,5678))

def check_links(data,name):
    """Both ends of every link in the edited graphs agree; nothing can boot here to find out otherwise."""
    for g in [data]+data.get('definitions',{}).get('subgraphs',[]):
        if not any((n.get('title') or '').startswith('Fit Frame') for n in g['nodes']):continue
        nodes={n['id']:n for n in g['nodes']}
        ids=[link_parts(l)[0] for l in g['links']]
        assert len(ids)==len(set(ids)),(name,'duplicate link id')
        for lid,source,slot,target,target_slot,kind in map(link_parts,g['links']):
            if source==-10:assert lid in g['inputs'][slot]['linkIds'],(name,lid)
            else:assert lid in nodes[source]['outputs'][slot]['links'],(name,lid)
            if target==-20:continue
            inp=nodes[target]['inputs'][target_slot]
            assert inp['link']==lid and (inp['type']=='*' or kind in inp['type'].split(',')),(name,lid,inp)
        for n in g['nodes']:
            for inp in n.get('inputs',[]):assert inp.get('link') is None or inp['link'] in ids,(name,n['id'],inp)
            for out in n.get('outputs',[]):assert all(x in ids for x in out.get('links') or []),(name,n['id'],out)
    every=[n['id'] for g in [data]+data.get('definitions',{}).get('subgraphs',[]) for n in g['nodes']]
    assert max(every)<=data['last_node_id'],(name,'last_node_id is stale')

def check_fitted(data,name):
    """No upload is cropped, and every edit frame takes its shape from the image."""
    graphs=[data]+data.get('definitions',{}).get('subgraphs',[])
    nodes=[(g,n) for g in graphs for n in g['nodes']]
    scales=[n for _,n in nodes if n['type']=='ImageScale']
    for n in scales:
        assert n.get('title')==FITTED and n['widgets_values'][3] in ('disabled','center'),(name,n['id'],'a fitted frame must not stretch')
    switches=[n for n in data['nodes'] if n.get('title')==EXACT]
    assert len(switches)<=1 and not any(n['widgets_values'][0] for n in switches),(name,'Exact Frame must be off by default')
    for g,n in nodes:
        if n['type'] in LATENTS and any(x['type']=='LoadImage' for x in data['nodes']):
            fits=[]
            for dim in ('width','height'):
                lid=next(i['link'] for i in n['inputs'] if i['name']==dim)
                source=next(link_parts(l)[1] for l in g['links'] if link_parts(l)[0]==lid)
                fits.append(next(x for x in g['nodes'] if x['id']==source).get('title'))
            assert fits==['Fit Frame Width','Fit Frame Height'],(name,n['id'],fits)
    return len(scales)

def check_api(api,name):
    assert not [n for n in api.values() if n['class_type']=='ImageScaleToTotalPixels'],(name,'stale automatic sizing')
    scales=[n for n in api.values() if n['class_type']=='ImageScale']
    assert scales and all(n['inputs']['crop'] in ('disabled','center') for n in scales),(name,'a fitted frame must not stretch')
    for n in api.values():
        for value in n['inputs'].values():
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str):assert value[0] in api,(name,value)

def check_studio():
    """Expand the studio node on a stub GraphBuilder: ComfyUI itself only runs in the GitHub build."""
    class Node:
        def __init__(self,kind,inputs):self.kind,self.inputs=kind,inputs
        def out(self,slot):return (self,slot)
    class GraphBuilder:
        def __init__(self):self.nodes=[]
        def node(self,kind,**inputs):
            self.nodes.append(Node(kind,inputs));return self.nodes[-1]
        def finalize(self):return self.nodes
    module=types.ModuleType('comfy_execution.graph_utils');module.GraphBuilder=GraphBuilder
    sys.modules.setdefault('comfy_execution',types.ModuleType('comfy_execution'));sys.modules['comfy_execution.graph_utils']=module
    spec=importlib.util.spec_from_file_location('acdev_studio',ROOT/'custom_nodes/acdev_studio/__init__.py')
    studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
    def expand(**extra):
        built=studio.FluxStudio().generate('p','n','base',1280,720,1,4,1.0,'euler','simple',False,1024,**extra)['expand']
        return {n.kind:n for n in built},built
    kinds,_=expand()
    assert (kinds['EmptyFlux2LatentImage'].inputs['width'],kinds['EmptyFlux2LatentImage'].inputs['height'])==(1280,720),'text to image keeps the typed size'
    assert 'ImageScale' not in kinds
    kinds,built=expand(reference_image=['10',0])
    fits=[n for n in built if n.kind=='ComfyMathExpression']
    assert [n.inputs['expression'] for n in fits]==['a if e else '+fit_expression('c','d',16),'b if e else '+fit_expression('d','c',16)]
    assert all(n.inputs['values.a']==1280 and n.inputs['values.b']==720 for n in fits)
    scale,latent=kinds['ImageScale'].inputs,kinds['EmptyFlux2LatentImage'].inputs
    assert scale['crop']=='center' and scale['image']==['10',0]
    assert all(n.inputs['values.e'] is False for n in fits)
    assert all(n.inputs['values.e'] is True for n in expand(reference_image=['10',0],exact_frame=True)[1] if n.kind=='ComfyMathExpression')
    assert kinds['VAEEncode'].inputs['pixels']==(kinds['ImageScale'],0)
    for inputs in (scale,latent):assert (inputs['width'],inputs['height'])==((fits[0],1),(fits[1],1))

check_studio()
count=0
fits=0
for path in sorted(ROOT.glob('versions/*/workflows/*.json')):
    if path.name.startswith('LTX25_'):continue
    d=json.loads(path.read_text())
    before=copy.deepcopy(d)
    apply_dimensions(d,(768,448) if 'Ingredients' in path.name else None)
    fit_references(d)
    assert d==before,(path.name,'dimensions were not packaged or packaging is not idempotent')
    fits+=check_fitted(d,path.name)
    check_links(d,path.name)
    api_path=path.parent.parent/'api'/path.name
    if api_path.exists() and 'Image_to_Image' in path.name:check_api(json.loads(api_path.read_text()),path.name)
    if any(n['type'] in ('AcdevFluxStudio','AcdevIdeogramStudio') for n in d['nodes']):continue
    found=inspect(d)
    assert found or 'Audio' in path.name and not any(n['type']=='SaveVideo' for n in d['nodes']),(path.name,'no editable render dimensions')
    count+=1
assert fits==8,fits
print('PASS: editable width/height reach render inputs; fitted frames never stretch; packaging is idempotent (%d workflows).'%count)
