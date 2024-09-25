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

def find_node_input(nw: NodeWrangler, node, name):
    socket = node.inputs[name]
    links = nw.find_from(socket)
    if len(links) == 0:
        return socket.default_value
    return links[0].from_socket

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
            nw.new_node(
                Nodes.Math,
                [
                    1.0,
                    find_node_input(nw, right, 'Transmission'),
                ],
                attrs={'operation': 'SUBTRACT'},
            )

    assert socket.type == 'SHADER'
    links = nw.find_from(socket)
    if len(links) == 0:
        return {}
    node = links[0].from_node
    name = type(node).__name__
    if name == Nodes.MixShader:
        factor = find_node_input(nw, node, 0)
        left = find_material_values(nw, node.inputs[1])
        right = find_material_values(nw, node.inputs[2])
        for k, v in right.items():
            if k in left:
                left[k] = mix_socket_values(factor, left[k], v)
            else:
                left[k] = v
        return left
    elif name == Nodes.PrincipledBSDF:
        return {
            'albedo': find_node_input(nw, node, 'Base Color'),
            'roughness': find_node_input(nw, node, 'Roughness'),
            'metalness': find_node_input(nw, node, 'Metallic'),
            'emission': multiply_socket_values(
                find_node_input(nw, node, 'Emission'),
                find_node_input(nw, node, 'Emission Strength'),
            ),
            'opacity': multiply_socket_values(
                find_node_input(nw, node, 'Alpha'),
                oneminus_socket_values(find_node_input(nw, node, 'Transmission')),
            ),
        }
    elif name == Nodes.DiffuseBSDF:
        return {
            'albedo': find_node_input(nw, node, 'Color'),
            # the diffuse node _technically_ has roughness, but it always looks rough regardless
            'roughness': 1.0,
        }
    elif name == Nodes.GlossyBSDF:
        return {
            'albedo': find_node_input(nw, node, 'Color'),
            'roughness': find_node_input(nw, node, 'Roughness'),
        }
    elif name == Nodes.Emission:
        return {
            'emission': multiply_socket_values(
                find_node_input(nw, node, 'Color'),
                find_node_input(nw, node, 'Strength'),
            ),
        }
    elif name == Nodes.TranslucentBSDF or name == Nodes.TransparentBSDF:
        return {
            'opacity': 0.0,
        }
    elif name == Nodes.RefractionBSDF or name == Nodes.GlassBSDF:
        return {
            'albedo': find_node_input(nw, node, 'Color'),
            'roughness': find_node_input(nw, node, 'Roughness'),
            'opacity': 0.0,
        }
    else:
        return {}

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
