"""Expose editable render dimensions without changing sampler or model settings."""
import json
import uuid
from pathlib import Path

LATENTS = {'EmptySD3LatentImage', 'EmptyFlux2LatentImage', 'EmptyLatentImage', 'EmptyLTXVLatentVideo'}
RESIZE = 'Resize reference to render width and height'
FITTED = 'Resize image to the fitted frame'
EXACT = 'Exact Frame: use Render Width and Height, cropping the image'
SIZE_NOTES = {
    'the reference is scaled to ~1 MP here and the output latent takes its size.':
        'the reference is scaled to ~1 MP here and kept whole. Render Width and Height set the output\'s area and the first reference sets its shape, in multiples of 16.',
    'Use `Empty Flux 2 Latent` node to customize image size':
        'Use Render Width and Render Height to set the output\'s area; the first reference sets its shape',
}

def link_parts(link):
    if isinstance(link, dict):
        return [link[k] for k in ('id','origin_id','origin_slot','target_id','target_slot','type')]
    return list(link[:6])

def remove_input_link(graph, node, slot):
    inp = node['inputs'][slot]
    lid = inp.get('link')
    if lid is None:
        return
    graph['links'] = [l for l in graph.get('links', []) if link_parts(l)[0] != lid]
    for source in graph.get('nodes', []):
        for output in source.get('outputs', []):
            if output.get('links'):
                output['links'] = [x for x in output['links'] if x != lid]
    for field in graph.get('inputs', []):
        if field.get('linkIds'):
            field['linkIds'] = [x for x in field['linkIds'] if x != lid]
    inp['link'] = None

def is_fitted(graph, node):
    fits = {n['id'] for n in graph['nodes'] if (n.get('title') or '').startswith('Fit Frame')}
    origins = {link_parts(l)[0]: link_parts(l)[1] for l in graph.get('links', [])}
    return any(origins.get(inp.get('link')) in fits for inp in node.get('inputs', []))

def apply_dimensions(data, default=None):
    """Return whether this workflow supports visual sizing; operate idempotently."""
    # The packaged subgraph already preserves the render controls and their wiring.
    if any(n.get('title') == 'Model internals' for n in data['nodes']):
        return True
    # Native studio nodes already expose width/height from INPUT_TYPES.
    if any(n['type'] in ('AcdevFluxStudio','AcdevIdeogramStudio') for n in data['nodes']):
        return True
    # Existing controls panels: unlink preset selectors, making their widgets editable.
    exposed = {}
    panel_types = {g['id'] for g in data.get('definitions',{}).get('subgraphs',[])}
    for node in data['nodes']:
        if node['type'] not in panel_types:
            continue
        for slot, inp in enumerate(node.get('inputs', [])):
            label = (inp.get('label') or inp['name']).lower()
            for dim in ('width','height'):
                if dim in label and inp.get('widget'):
                    exposed[dim] = (node, slot)
    if len(exposed) == 2:
        for node, slot in exposed.values():
            remove_input_link(data, node, slot)
        # Preset-only selectors no longer drive the controls panel.
        data['nodes'] = [n for n in data['nodes'] if n['type'] != 'ResolutionSelector' or any(o.get('links') for o in n.get('outputs', []))]
        return True

    definitions = {g['id']: g for g in data.get('definitions',{}).get('subgraphs',[])}
    # Traverse instantiated subgraphs, avoiding unused definitions in upstream templates.
    contexts = []
    def walk(graph, parents):
        contexts.append((graph, parents))
        for node in graph['nodes']:
            if node['type'] in definitions:
                walk(definitions[node['type']], parents+[(graph,node)])
    walk(data, [])
    targets = []
    for graph, parents in contexts:
        for node in graph['nodes']:
            if node['type'] in LATENTS:
                # Fit Frame nodes already read the Render controls on this frame's behalf.
                if is_fitted(graph, node):
                    continue
                for index, dim in enumerate(('width','height')):
                    inputs = node.setdefault('inputs', [])
                    slot = next((i for i,x in enumerate(inputs) if x['name'] == dim), None)
                    if slot is None:
                        slot = len(inputs); inputs.append({'name':dim,'type':'INT','widget':{'name':dim},'link':None})
                    targets.append((graph,parents,node,slot,dim))
            elif node['type'] == 'ImageScaleToTotalPixels' or (node['type']=='ResizeImageMaskNode' and default==(768,448)):
                # Explicit dimensions replace automatic megapixel sizing for image edits.
                node['type'] = 'ImageScale'
                node.setdefault('properties',{})['Node name for S&R'] = 'ImageScale'
                node['title'] = RESIZE
                node['inputs'] = [x for x in node.get('inputs',[]) if x['name'] in ('image','input')]
                node['inputs'][0]['name']='image'
                method = 'lanczos'
                size = default or (1280,720)
                node['widgets_values'] = [method,size[0],size[1],'center']
                node.pop('widgets_values_named',None)
                for dim in ('width','height'):
                    slot=len(node['inputs']);node['inputs'].append({'name':dim,'type':'INT','widget':{'name':dim},'link':None})
                    targets.append((graph,parents,node,slot,dim))
            elif node['type']=='ImageScale' and node.get('title')==RESIZE:
                for slot, inp in enumerate(node['inputs']):
                    if inp['name'] in ('width','height'):targets.append((graph,parents,node,slot,inp['name']))
    if not targets:
        return False
    if default is None:
        latent = next((n for _,_,n,_,_ in targets if n['type'] in LATENTS), None)
        default = tuple(latent['widgets_values'][:2]) if latent else (1280,720)
    max_node=max(n['id'] for graph,_ in contexts for n in graph['nodes'])
    max_link=max([link_parts(l)[0] for graph,_ in contexts for l in graph.get('links',[])]+[0])
    controls={}
    for index,dim in enumerate(('width','height')):
        control=next((n for n in data['nodes'] if n.get('title')=='Render '+dim.title() and n['type']=='PrimitiveInt'),None)
        if control is None:
            max_node+=1
            control={'id':max_node,'type':'PrimitiveInt','title':'Render '+dim.title(),'pos':[-400,index*150],'size':[300,110],'flags':{},'order':0,'mode':0,
                     'inputs':[],'outputs':[{'name':'INT','type':'INT','links':[]}], 'properties':{'Node name for S&R':'PrimitiveInt'},'widgets_values':[default[index],'fixed']}
            data['nodes'].append(control)
        controls[dim]=control
    def connect(graph,node,slot,origin,origin_slot):
        nonlocal max_link
        old = node['inputs'][slot].get('link')
        if old is not None:
            parts = next(link_parts(l) for l in graph['links'] if link_parts(l)[0] == old)
            if parts[1:3] == [origin,origin_slot]:return
        remove_input_link(graph,node,slot)
        max_link+=1;lid=max_link
        values=[lid,origin,origin_slot,node['id'],slot,'INT']
        if graph is data and (not graph.get('links') or not isinstance(graph['links'][0],dict)):
            graph.setdefault('links',[]).append(values)
        else:
            graph.setdefault('links',[]).append(dict(zip(('id','origin_id','origin_slot','target_id','target_slot','type'),values)))
        node['inputs'][slot]['link']=lid
        if origin==-10:
            graph['inputs'][origin_slot]['linkIds'].append(lid)
        else:
            source=next(n for n in graph['nodes'] if n['id']==origin)
            out=source['outputs'][origin_slot];out['links']=(out.get('links') or [])+[lid]
        graph.setdefault('state',{})['lastLinkId']=lid
    boundary={}
    def route(graph,parents,node,slot,dim):
        if graph is data:
            connect(graph,node,slot,controls[dim]['id'],0);return
        key=(graph['id'],dim)
        if key not in boundary:
            name='render_'+dim
            inputs=graph.setdefault('inputs',[])
            idx=next((i for i,x in enumerate(inputs) if x['name']==name),None)
            if idx is None:
                idx=len(inputs);inputs.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,graph['id']+'/'+name)), 'name':name,'label':'Render '+dim.title(),'type':'INT','linkIds':[],'pos':[0,20*idx]})
            boundary[key]=idx
        idx=boundary[key]
        connect(graph,node,slot,-10,idx)
        parent,instance=parents[-1]
        ins=instance.setdefault('inputs',[])
        instance_slot=next((i for i,x in enumerate(ins) if x['name']=='render_'+dim),None)
        if instance_slot is None:
            instance_slot=len(ins);ins.append({'name':'render_'+dim,'label':'Render '+dim.title(),'type':'INT','link':None})
            instance['size'][1]=max(instance['size'][1],120+30*len(ins))
        # Only route once per instance, even when it drives several internal nodes.
        if ins[instance_slot].get('link') is None:
            route(parent,parents[:-1],instance,instance_slot,dim)
    for graph,parents,node,slot,dim in targets:
        route(graph,parents,node,slot,dim)
    # Keep an established controls panel compact when its widget ordering is explicit.
    control_ids={c['id'] for c in controls.values()}
    dimension_links=[link_parts(l) for l in data['links'] if link_parts(l)[1] in control_ids]
    destinations={l[3] for l in dimension_links}
    if len(destinations)==1:
        panel=next(n for n in data['nodes'] if n['id'] in destinations)
        widgets=[i for i in panel.get('inputs',[]) if i.get('widget')]
        values=panel.get('widgets_values',[])
        if panel['type'] in definitions and len(values)==len(widgets):
            for dim in ('width','height'):
                slot=next(i for i,x in enumerate(panel['inputs']) if x['name']=='render_'+dim)
                remove_input_link(data,panel,slot)
                inp=panel['inputs'][slot];inp['widget']={'name':inp['name']}
                values.append(controls[dim]['widgets_values'][0])
                panel.setdefault('widgets_values_named',{})[inp['name']]=values[-1]
            data['nodes']=[n for n in data['nodes'] if n['id'] not in control_ids]
    data['last_node_id']=max_node;data['last_link_id']=max_link
    data.setdefault('state',{})['lastNodeId']=max_node
    return True

def sync_api(api, ui):
    """Keep flat API fixtures aligned with the UI dimensions used by GPU tests."""
    for node in ui['nodes']:
        nid=str(node['id'])
        if node['type']=='PrimitiveInt' and node.get('title','').startswith('Render '):
            api[nid]={'class_type':'PrimitiveInt','inputs':{'value':node['widgets_values'][0]}}
        elif nid in api:
            if node['type']=='ImageScale' and api[nid]['class_type']=='ImageScaleToTotalPixels':
                old=api[nid]['inputs'];api[nid]={'class_type':'ImageScale','inputs':{'image':old['image'],'upscale_method':old['upscale_method'],'crop':'center'}}
            for inp in node.get('inputs',[]):
                if inp['name'] in ('width','height') and inp.get('link') is not None:
                    link=next(link_parts(l) for l in ui['links'] if link_parts(l)[0]==inp['link'])
                    api[nid]['inputs'][inp['name']]=[str(link[1]),link[2]]

def fit_expression(mine, other, step):
    """One side of a frame with area a*b and the proportions of a c x d image, on the model's grid."""
    return 'max(64,round(sqrt(a*b*%s/%s)/%d)*%d)'%(mine,other,step,step)

def origin(graph, node, name):
    """The (node id, slot) feeding a named input."""
    lid = next(inp['link'] for inp in node['inputs'] if inp['name'] == name)
    return next(link_parts(l)[1:3] for l in graph['links'] if link_parts(l)[0] == lid)

def fit_frame_to_image(data, graph, image, width, height, targets, step=16):
    """Point each target's width and height at a frame fitted to an image, in a root graph or a subgraph.

    `image`, `width` and `height` are (node id, slot) origins: the Render controls keep setting the frame's
    area while the image sets its proportions, so a portrait stays a portrait and a typed size that already
    matches the image comes back unchanged.
    """
    groups = [data] + data.get('definitions', {}).get('subgraphs', [])
    next_node = max([n['id'] for g in groups for n in g['nodes']] + [data.get('last_node_id') or 0])
    next_link = max([link_parts(l)[0] for g in groups for l in g.get('links', [])] + [data.get('last_link_id') or 0])
    flat = bool(graph.get('links')) and not isinstance(graph['links'][0], dict)
    nodes = {n['id']: n for n in graph['nodes']}
    def add(node):
        nonlocal next_node
        next_node += 1
        node.update(id=next_node, flags={}, order=0, mode=0, properties={'Node name for S&R': node['type']})
        graph['nodes'].append(node)
        nodes[next_node] = node
        return node
    def connect(source, source_slot, target, target_slot, kind):
        nonlocal next_link
        next_link += 1
        values = [next_link, source, source_slot, target['id'], target_slot, kind]
        graph['links'].append(values if flat else dict(zip(('id','origin_id','origin_slot','target_id','target_slot','type'), values)))
        target['inputs'][target_slot]['link'] = next_link
        if source == -10:
            graph['inputs'][source_slot]['linkIds'].append(next_link)
        else:
            output = nodes[source]['outputs'][source_slot]
            output['links'] = (output.get('links') or []) + [next_link]
    x, y = targets[0]['pos']
    getter = add({'type': 'GetImageSize', 'title': 'Size of your image', 'pos': [x - 340, y + 330], 'size': [320, 120], 'widgets_values': [],
                  'inputs': [{'name': 'image', 'type': 'IMAGE', 'link': None}],
                  'outputs': [{'name': name, 'type': 'INT', 'links': []} for name in ('width', 'height', 'batch_size')]})
    def fit(title, expression, row):
        return add({'type': 'ComfyMathExpression', 'title': title, 'pos': [x, y + 330 + row * 200], 'size': [320, 180], 'widgets_values': [expression],
                    'inputs': [{'name': 'expression', 'type': 'STRING', 'link': None, 'widget': {'name': 'expression'}}] +
                              [{'name': 'values.' + letter, 'type': 'FLOAT,INT,BOOLEAN', 'link': None} for letter in 'abcd'],
                    'outputs': [{'name': 'FLOAT', 'type': 'FLOAT', 'links': []}, {'name': 'INT', 'type': 'INT', 'links': []}, {'name': 'BOOL', 'type': 'BOOLEAN', 'links': []}]})
    fit_w = fit('Fit Frame Width', fit_expression('c', 'd', step), 0)
    fit_h = fit('Fit Frame Height', fit_expression('d', 'c', step), 1)
    connect(image[0], image[1], getter, 0, 'IMAGE')
    for node in (fit_w, fit_h):
        connect(width[0], width[1], node, 1, 'INT')
        connect(height[0], height[1], node, 2, 'INT')
        connect(getter['id'], 0, node, 3, 'INT')
        connect(getter['id'], 1, node, 4, 'INT')
    for target in targets:
        for name, fitted in (('width', fit_w), ('height', fit_h)):
            slot = next(i for i, inp in enumerate(target['inputs']) if inp['name'] == name)
            remove_input_link(graph, target, slot)
            connect(fitted['id'], 1, target, slot, 'INT')
    data['last_node_id'], data['last_link_id'] = next_node, next_link
    data.setdefault('state', {}).update(lastNodeId=next_node, lastLinkId=next_link)
    if 'state' in graph:
        graph['state'].update(lastNodeId=next_node, lastLinkId=next_link)

def fit_references(data):
    """Keep whole uploads: each edit reference fits its own shape and the first one shapes the output."""
    for graph in [data] + data.get('definitions', {}).get('subgraphs', []):
        scales = [n for n in graph['nodes'] if n['type'] == 'ImageScale' and n.get('title') == RESIZE]
        latents = [n for n in graph['nodes'] if n['type'] in LATENTS]
        # The scheduler's GetImageSize reads the reference that sets the output's frame.
        sized = {link_parts(l)[1] for l in graph.get('links', []) if link_parts(l)[3] in
                 {n['id'] for n in graph['nodes'] if n['type'] == 'GetImageSize'}}
        for scale in scales:
            image, width, height = (origin(graph, scale, name) for name in ('image', 'width', 'height'))
            fit_frame_to_image(data, graph, image, width, height, [scale] + (latents if scale['id'] in sized else []))
            scale['title'] = FITTED
            scale['widgets_values'][3] = 'disabled'
        # Upstream's multi-reference graphs size the output from the reference and leave Render unplugged.
        for node in graph['nodes']:
            if node['type'] != 'ReferenceMultiLatent' or not node['outputs'][2].get('links'):
                continue
            latent = next(n for n in latents if not n['outputs'][0].get('links'))
            moved = node['outputs'][2]['links']
            for link in graph['links']:
                if link[0] in moved:
                    link[1:3] = [latent['id'], 0]
            latent['outputs'][0]['links'], node['outputs'][2]['links'] = list(moved), []
            fit_frame_to_image(data, graph, origin(graph, node, 'images.image0'), origin(graph, latent, 'width'), origin(graph, latent, 'height'), [latent])
    for node in data['nodes']:
        if node['type'] == 'MarkdownNote':
            for old, new in SIZE_NOTES.items():
                node['widgets_values'][0] = node['widgets_values'][0].replace(old, new)

def add_exact_frame(data):
    """Add one Exact Frame switch, off by default, to whichever fits shape the output; idempotent.

    On, the typed Render size stands and the image that shapes the output is centre-cropped to it.
    Further references keep fitting their own shape, so they stay whole either way.
    """
    groups = [data] + data.get('definitions', {}).get('subgraphs', [])
    if any(n.get('title') == EXACT for n in data['nodes']):
        return False
    def shaping(graph):
        nodes = {n['id']: n for n in graph['nodes']}
        fits = [n for n in graph['nodes'] if (n.get('title') or '').startswith('Fit Frame')]
        targets = {n['id']: {link_parts(l)[3] for l in graph['links'] if link_parts(l)[1] == n['id']} for n in fits}
        chosen = [n for n in fits if any(nodes[t]['type'] in LATENTS for t in targets[n['id']] if t in nodes)]
        return chosen, [nodes[t] for n in chosen for t in targets[n['id']] if t in nodes and nodes[t]['type'] == 'ImageScale']
    plan = [(g, *shaping(g)) for g in groups]
    plan = [item for item in plan if item[1]]
    if not plan:
        return False
    next_node = max([n['id'] for g in groups for n in g['nodes']] + [data.get('last_node_id') or 0]) + 1
    next_link = max([link_parts(l)[0] for g in groups for l in g.get('links', [])] + [data.get('last_link_id') or 0])
    switch = {'id': next_node, 'type': 'PrimitiveBoolean', 'title': EXACT, 'pos': [-400, 330], 'size': [300, 100], 'flags': {}, 'order': 0, 'mode': 0,
              'inputs': [], 'outputs': [{'name': 'BOOLEAN', 'type': 'BOOLEAN', 'links': []}],
              'properties': {'Node name for S&R': 'PrimitiveBoolean'}, 'widgets_values': [False]}
    data['nodes'].append(switch)
    flat = not data['links'] or not isinstance(data['links'][0], dict)
    def link(graph, source, source_slot, target, target_slot):
        nonlocal next_link
        next_link += 1
        values = [next_link, source, source_slot, target['id'], target_slot, 'BOOLEAN']
        as_list = graph is data and flat or (graph['links'] and not isinstance(graph['links'][0], dict))
        graph['links'].append(values if as_list else dict(zip(('id', 'origin_id', 'origin_slot', 'target_id', 'target_slot', 'type'), values)))
        target['inputs'][target_slot]['link'] = next_link
        return next_link
    for graph, fits, scales in plan:
        if graph is data:
            origin_id, origin_slot = switch['id'], 0
        else:
            origin_id, origin_slot = -10, len(graph['inputs'])
            graph['inputs'].append({'id': str(uuid.uuid5(uuid.NAMESPACE_URL, graph['id'] + '/exact_frame')), 'name': 'exact_frame', 'label': 'Exact Frame',
                                    'type': 'BOOLEAN', 'linkIds': [], 'pos': [0, 0]})
            for instance in (n for n in data['nodes'] if n['type'] == graph['id']):
                instance['inputs'].append({'name': 'exact_frame', 'label': 'Exact Frame', 'type': 'BOOLEAN', 'link': None})
                switch['outputs'][0]['links'].append(link(data, switch['id'], 0, instance, len(instance['inputs']) - 1))
        for node in fits:
            typed = 'a' if node['title'].endswith('Width') else 'b'
            node['widgets_values'][0] = '%s if e else %s' % (typed, node['widgets_values'][0])
            node['inputs'].append({'name': 'values.e', 'type': 'FLOAT,INT,BOOLEAN', 'link': None})
            made = link(graph, origin_id, origin_slot, node, len(node['inputs']) - 1)
            if origin_id == -10:
                graph['inputs'][origin_slot]['linkIds'].append(made)
            else:
                switch['outputs'][0]['links'].append(made)
        for scale in scales:
            scale['widgets_values'][3] = 'center'
    data['last_node_id'], data['last_link_id'] = next_node, next_link
    for graph in [data] + [item[0] for item in plan]:
        graph.setdefault('state', {}).update(lastNodeId=next_node, lastLinkId=next_link)
    return True

def sync_fitted_api(api, ui):
    """Flatten fitted subgraphs into the API fixtures under ComfyUI's instance:node ids."""
    definitions = {g['id']: g for g in ui.get('definitions', {}).get('subgraphs', [])}
    for node in ui['nodes']:
        key = str(node['id'])
        title = node.get('title') or ''
        if title == EXACT:
            api[key] = {'class_type': 'PrimitiveBoolean', 'inputs': {'value': node['widgets_values'][0]}}
        elif title.startswith('Fit Frame') and key in api and len([i for i in node['inputs'] if i['name'].startswith('values.')]) == 5:
            link = next(link_parts(l) for l in ui['links'] if link_parts(l)[0] == next(i['link'] for i in node['inputs'] if i['name'] == 'values.e'))
            api[key]['inputs'].update({'expression': node['widgets_values'][0], 'values.e': [str(link[1]), link[2]]})
        elif node['type'] == 'ImageScale' and title == FITTED and key in api:
            api[key]['inputs']['crop'] = node['widgets_values'][3]
    for instance in ui['nodes']:
        graph = definitions.get(instance['type'])
        if graph is None or instance.get('mode') == 4:
            continue
        def ref(node, name):
            source = origin(graph, node, name)
            if source[0] == -10:
                outer = origin(ui, instance, graph['inputs'][source[1]]['name'])
                return [str(outer[0]), outer[1]]
            return ['%s:%s' % (instance['id'], source[0]), source[1]]
        for node in graph['nodes']:
            key = '%s:%s' % (instance['id'], node['id'])
            title = node.get('title') or ''
            if node['type'] == 'ImageScale' and title == FITTED:
                api[key] = {'class_type': 'ImageScale', 'inputs': {'image': ref(node, 'image'), 'upscale_method': node['widgets_values'][0],
                                                                   'width': ref(node, 'width'), 'height': ref(node, 'height'), 'crop': node['widgets_values'][3]}}
            elif node['type'] == 'GetImageSize' and title == 'Size of your image':
                api[key] = {'class_type': 'GetImageSize', 'inputs': {'image': ref(node, 'image')}}
            elif title.startswith('Fit Frame'):
                api[key] = {'class_type': 'ComfyMathExpression', 'inputs': {'expression': node['widgets_values'][0],
                            **{inp['name']: ref(node, inp['name']) for inp in node['inputs'] if inp['name'].startswith('values.')}}}
            elif node['type'] in LATENTS and is_fitted(graph, node) and key in api:
                api[key]['inputs'].update(width=ref(node, 'width'), height=ref(node, 'height'))

def main():
    root=Path(__file__).resolve().parents[1]
    for path in sorted(root.glob('versions/*/workflows/*.json')):
        if path.name.startswith('LTX25_'):continue
        data=json.loads(path.read_text())
        defaults=(768,448) if 'Ingredients' in path.name else None
        apply_dimensions(data,defaults)
        fit_references(data)
        add_exact_frame(data)
        text=json.dumps(data,indent=2,ensure_ascii=False)+'\n'
        if json.loads(path.read_text())!=data:path.write_text(text)
        api_path=path.parent.parent/'api'/path.name
        if api_path.exists():
            api=json.loads(api_path.read_text());sync_api(api,data);sync_fitted_api(api,data)
            api_path.write_text(json.dumps(api,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
