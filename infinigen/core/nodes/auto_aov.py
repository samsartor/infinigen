from infinigen.core.nodes.node_wrangler import NodeWrangler, infer_output_socket
from infinigen.core.nodes.node_info import Nodes
import bpy

def socket_value_kind(socket_value):
    kind = None
    socket = infer_output_socket(socket_value)
    if socket is not None:
        if socket.type == 'RGBA' or socket.type == 'VECTOR':
            kind = 'Color'
        elif socket.type == 'VALUE':
            kind = 'Value'
    elif isinstance(socket_value, bpy.types.bpy_prop_array) and len(socket_value) == 4:
        kind = 'Color'        
    elif isinstance(socket_value, float):
        kind = 'Value'
    return kind

def extract_node_input(nw: NodeWrangler, node, name):
    to_socket = node.inputs[name]
    to_kind = socket_value_kind(to_socket)
    links = nw.find_from(to_socket)
    if len(links) == 0:
        return to_socket.default_value
    from_socket = links[0].from_socket
    from_kind = socket_value_kind(from_socket)
    if to_kind == 'Value' and from_kind == 'Color':
        from_socket = nw.new_node(Nodes.RGBToBW, [from_socket])
    elif to_kind == 'Color' and from_kind == 'Value':
        from_socket = nw.new_node(Nodes.CombineRGB, [from_socket, from_socket, from_socket])
    return from_socket

def find_material_values(nw: NodeWrangler, socket):
    def mix_socket_values(factor, left, right):
        kind = socket_value_kind(left)
        if kind is None or kind != socket_value_kind(right):
            raise ValueError(f'attempted to mix {type(left)} with {type(right)}')
        if kind == 'Color':
            return nw.new_node(Nodes.MixRGB, input_kwargs={'Factor': factor, 'A': left, 'B': right})
        if kind == 'Value':
            return nw.new_node(Nodes.Mix, input_kwargs={'Factor': factor, 'A': left, 'B': right})

    def multiply_socket_values(left, right):
        lkind = socket_value_kind(left)
        rkind = socket_value_kind(right)
        if lkind is None or rkind is None:
            raise ValueError(f'attempted to multiply {left} by {right}')
        if isinstance(left, float) and isinstance(right, float):
            return left * right
        if lkind == 'Color' or rkind == 'Color':
            if isinstance(left, float):
                left = [left, left, left, left]
            if isinstance(right, float):
                right = [right, right, right, right]
            return nw.new_node(Nodes.MixRGB, input_kwargs={'A': left, 'B': right}, attrs={'blend_type': 'MULTIPLY'})
        else:
            return nw.new_node(Nodes.Math, [left, right], attrs={'operation': 'MULTIPLY'})

    def oneminus_socket_values(right):
        if isinstance(right, float):
            return 1.0 - right
        else:
            return nw.new_node(
                Nodes.Math,
                [1.0, right],
                attrs={'operation': 'SUBTRACT'},
            )
            
    def pow_socket_values(left, right):
        if isinstance(left, float) and isinstance(right, float):
            return left ** right
        else:
            return nw.new_node(
                Nodes.Math,
                [left, right],
                attrs={'operation': 'POWER'},
            )

    assert socket.type == 'SHADER'
    links = nw.find_from(socket)
    if len(links) == 0:
        return {}
    node = links[0].from_node
    name = type(node).__name__
    if name == Nodes.MixShader:
        factor = extract_node_input(nw, node, 0)
        left = find_material_values(nw, node.inputs[1])
        right = find_material_values(nw, node.inputs[2])
        for k, v in right.items():
            if k in left:
                if k == 'roughness':
                    # unfortunately blending materials with different roughness is not the same as blending their roughness, but we can approximate
                    # Burley 2012 suggest when "interpolating" or mipmapping materials to use the roughness^2
                    left[k] = pow_socket_values(mix_socket_values(factor, pow_socket_values(left[k], 2.0), pow_socket_values(v, 2.0)), 0.5)
                else:
                    left[k] = mix_socket_values(factor, left[k], v)
            else:
                # TODO: this isn't quite correct in some cases
                # for example, a 50% mixed diffuse+emissive has 50% emission
                left[k] = v
        return left
    elif name == Nodes.PrincipledBSDF:
        return {
            'albedo': extract_node_input(nw, node, 'Base Color'),
            'roughness': extract_node_input(nw, node, 'Roughness'),
            'metalness': extract_node_input(nw, node, 'Metallic'),
            'emission': multiply_socket_values(
                extract_node_input(nw, node, 'Emission'),
                extract_node_input(nw, node, 'Emission Strength'),
            ),
            'opacity': multiply_socket_values(
                extract_node_input(nw, node, 'Alpha'),
                oneminus_socket_values(extract_node_input(nw, node, 'Transmission')),
            ),
        }
    elif name == Nodes.DiffuseBSDF:
        return {
            'albedo': extract_node_input(nw, node, 'Color'),
            # the diffuse node _technically_ has roughness, but it always looks 100% rough relative to Glossy/Principaled
            'roughness': 1.0,
            'opacity': 1.0,
        }
    elif name == Nodes.GlossyBSDF:
        return {
            'albedo': extract_node_input(nw, node, 'Color'),
            'roughness': extract_node_input(nw, node, 'Roughness'),
            'opacity': 1.0,
        }
    elif name == Nodes.Emission:
        return {
            'emission': multiply_socket_values(
                extract_node_input(nw, node, 'Color'),
                extract_node_input(nw, node, 'Strength'),
            ),
        }
    elif name == Nodes.TranslucentBSDF or name == Nodes.TransparentBSDF:
        return {
            'opacity': 0.0,
        }
    elif name == Nodes.RefractionBSDF or name == Nodes.GlassBSDF:
        return {
            # technically glass has a color, but it is transmission not reflection so we don't count it
            'roughness': extract_node_input(nw, node, 'Roughness'),
            'opacity': 0.0,
        }
    elif name == 'ShaderNodeGroup':
        if not any(map(lambda socket: socket.name.startswith('aov/'), node.outputs)):
            auto_group_aovs(NodeWrangler(node.node_tree))
        return {
            socket.name.removeprefix('aov/'): socket
            for socket in node.outputs
            if socket.name.startswith('aov/')
        }
    else:
        return {}

def auto_group_aovs(nw: NodeWrangler):
    group_output = nw.find(Nodes.GroupOutput)[0]
    surface = [socket for socket in group_output.inputs if socket.type == 'SHADER'][0]
    values = find_material_values(nw, surface)
    for name, value in values.items():
        kind = socket_value_kind(value)
        if kind is None:
            raise ValueError(f'attempted to create a group output for {value}')
        kind = {
            'Value': 'NodeSocketFloat',
            'Color': 'NodeSocketColor',
        }[kind]
        nw.node_group.outputs.new(kind, f'aov/{name}')
        nw.connect_input(group_output.inputs[f'aov/{name}'], value)
    
def auto_material_aovs(nw: NodeWrangler, clear_existing=True):
    if clear_existing:
        existing = nw.find(Nodes.OutputAOV)
        while len(existing) > 0:
            node = existing.pop()
            if all(map(lambda n: not n.is_linked, node.outputs)):
                for socket in node.inputs:
                    for link in nw.find_from(socket):
                        existing.append(link.from_node)
                nw.node_group.nodes.remove(node)

    kinds = {}
    outputs = nw.find(Nodes.MaterialOutput)
    if len(outputs) != 1:
        return kinds
    surface = outputs[0].inputs['Surface']
    values = find_material_values(nw, surface)
    for name, value in values.items():
        kind = socket_value_kind(value)
        if kind is None:
            raise ValueError(f'attempted to create an output aov for {value}')
        nw.new_node(Nodes.OutputAOV, attrs={'name': name}, input_kwargs={kind: value})
        kinds[name] = kind.upper()
    return kinds

def auto_all_material_aovs():
    kinds = {}
    for m in bpy.data.materials:
        if m.use_nodes:
            kinds.update(auto_material_aovs(NodeWrangler(m.node_tree)))
    return kinds
