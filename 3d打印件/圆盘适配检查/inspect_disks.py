from pathlib import Path
from collections import Counter
import json
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 12
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.world.color = (0.45, 0.45, 0.45)
mat = bpy.data.materials.new('Inspection orange')
mat.use_nodes = True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.7, 0.18, 0.025, 1)
reports = {}
for name in ['base1', 'base-2', 'tapa-v2', 'case_lid', 'gear_servo']:
    bpy.ops.wm.stl_import(filepath=str(ROOT / (name + '.stl')))
    obj = bpy.context.object
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    coords = [v.co for v in obj.data.vertices]
    bounds = [[min(p[i] for p in coords), max(p[i] for p in coords)] for i in range(3)]
    reports[name] = {'bounds_mm': bounds, 'z_levels': Counter(round(p.z, 4) for p in coords).most_common(20)}
    center = Vector([(a+b)/2 for a,b in bounds])
    size = max(b-a for a,b in bounds)
    for tag, direction in [('top', (0, -0.4, 1)), ('bottom', (0, 0.4, -1))]:
        bpy.ops.object.camera_add(location=center+Vector(direction).normalized()*size*2)
        camera = bpy.context.object
        camera.rotation_euler = (center-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = size*1.25
        camera.data.clip_end = 10000
        scene.camera = camera
        bpy.ops.object.light_add(type='AREA', location=center+Vector((-0.5,-0.7,1 if tag=='top' else -1))*size)
        lamp = bpy.context.object
        lamp.data.energy = 6*size*size
        lamp.data.size = size
        lamp.rotation_euler = (center-lamp.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath = str(OUT / (name+'_'+tag+'.png'))
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.objects.remove(lamp, do_unlink=True)
    bpy.data.objects.remove(obj, do_unlink=True)
(OUT / 'original-dimensions.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
print(json.dumps(reports, indent=2))
