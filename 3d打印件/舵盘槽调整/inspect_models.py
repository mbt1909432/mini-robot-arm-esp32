from pathlib import Path
from collections import Counter
import bpy
import json
from mathutils import Vector

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
report = {}
for name in ['arm-1', 'arm-2', 'arm_support', 'gear_arm1', 'gear_arm2']:
    bpy.ops.wm.stl_import(filepath=str(ROOT / (name + '.stl')))
    obj = bpy.context.object
    coords = [v.co for v in obj.data.vertices]
    report[name] = {
        'bounds': [[min(v[i] for v in coords), max(v[i] for v in coords)] for i in range(3)],
        'levels': [{str(k): n for k, n in Counter(round(v[i], 3) for v in coords).most_common(25)} for i in range(3)],
        'vertices': len(coords),
    }
    obj.hide_render = True

print(json.dumps(report, indent=2))
(OUT / 'original_geometry.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 12
scene.render.resolution_x = 800
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.world.color = (0.65, 0.65, 0.65)
mat = bpy.data.materials.new('Orange plastic')
mat.diffuse_color = (0.8, 0.19, 0.025, 1)
mat.use_nodes = True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.6, 0.12, 0.015, 1)
for name in ['arm-1', 'arm-2']:
    obj = bpy.data.objects[name]
    obj.hide_render = False
    obj.data.materials.append(mat)
    bounds = report[name]['bounds']
    center = Vector([(a+b)/2 for a,b in bounds])
    size = max(b-a for a,b in bounds)
    for tag, direction in [('top', (0, 0, 1)), ('bottom', (0, 0, -1)), ('angle', (0, -1, 1.8))]:
        bpy.ops.object.camera_add(location=center + Vector(direction).normalized() * size * 2)
        camera = bpy.context.object
        camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = size * 1.2
        scene.camera = camera
        bpy.ops.object.light_add(type='AREA', location=center + Vector((0.1, -0.6, 1 if tag != 'bottom' else -1)) * size)
        light = bpy.context.object
        light.data.energy = 3 * size * size
        light.data.shape = 'DISK'
        light.data.size = size
        light.rotation_euler = (center-light.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(OUT / (name + '_' + tag + '.png'))
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.objects.remove(light, do_unlink=True)
    obj.hide_render = True
