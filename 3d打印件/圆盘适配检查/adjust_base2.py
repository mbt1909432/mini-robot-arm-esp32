"""Blender batch: conservative clearance trial for the MG90S raised housing."""
from pathlib import Path
import hashlib
import json
import math
import bpy
import bmesh
from mathutils import Vector

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'base-2.stl'
CX, CY = 0.00478, 0.0
RADIUS, FLOOR, MOUTH = 11.0, -8.25, -14.75


def select(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def report(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    remaining = set(bm.verts)
    components = 0
    while remaining:
        stack = [remaining.pop()]
        components += 1
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other)
                    stack.append(other)
    result = {
        'non_manifold_edges': sum(not e.is_manifold for e in bm.edges),
        'inconsistent_edges': sum(not e.is_contiguous for e in bm.edges),
        'degenerate_faces': sum(f.calc_area() < 1e-9 for f in bm.faces),
        'connected_components': components,
        'volume_mm3': bm.calc_volume(signed=True),
        'bounds_mm': [[min(v.co[i] for v in bm.verts), max(v.co[i] for v in bm.verts)] for i in range(3)],
        'triangles': len(bm.faces),
    }
    bm.free()
    assert result['non_manifold_edges'] == 0, result
    assert result['inconsistent_edges'] == 0, result
    assert result['degenerate_faces'] == 0, result
    assert components == 1 and result['volume_mm3'] > 0, result
    return result


def boolean(obj, cutter, operation):
    select(obj)
    mod = obj.modifiers.new('MG90S housing clearance', 'BOOLEAN')
    mod.operation = operation
    mod.solver = 'EXACT'
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1e-5)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def export(obj, filename):
    select(obj)
    expected = report(obj)
    bpy.ops.wm.stl_export(filepath=str(OUT / filename), export_selected_objects=True)
    bpy.ops.wm.stl_import(filepath=str(OUT / filename))
    imported = bpy.context.object
    result = report(imported)
    assert abs(expected['volume_mm3']-result['volume_mm3']) < 0.001
    bpy.data.objects.remove(imported, do_unlink=True)
    return result


bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.wm.stl_import(filepath=str(SOURCE))
arm = bpy.context.object
arm.name = 'base-2 MG90S clearance trial D22 depth6.5'
original = arm.copy()
original.data = arm.data.copy()
bpy.context.collection.objects.link(original)
original.name = 'Original base-2 reference'
before = report(original)

# Circular clearance remains valid as the rotating base moves around the servo.
n = 160
levels = [(11.3, MOUTH-1), (11.3, MOUTH), (RADIUS, MOUTH+0.3), (RADIUS, FLOOR)]
verts = [(CX+r*math.cos(i*2*math.pi/n), CY+r*math.sin(i*2*math.pi/n), z) for r,z in levels for i in range(n)]
faces = [tuple(reversed(range(n))), tuple(range(3*n,4*n))]
for level in range(3):
    for i in range(n):
        j = (i+1) % n
        faces.append((level*n+i,level*n+j,(level+1)*n+j,(level+1)*n+i))
mesh = bpy.data.meshes.new('Clearance cutter mesh')
mesh.from_pydata(verts, [], faces)
mesh.update()
cutter = bpy.data.objects.new('D22 depth6.5 entry chamfer0.3 cutter', mesh)
bpy.context.collection.objects.link(cutter)
boolean(arm, cutter, 'DIFFERENCE')
after = report(arm)
assert before['bounds_mm'] == after['bounds_mm']
assert 500 < before['volume_mm3']-after['volume_mm3'] < 700
# Preserve all upper connection and support geometry above the new recess roof.
upper = [v.co.copy() for v in original.data.vertices if v.co.z > FLOOR+0.001]
modified = [v.co.copy() for v in arm.data.vertices]
assert all(min((p-q).length for q in modified) < 1e-5 for p in upper)

thicknesses = []
for radius in [4.0,5.0,6.0,7.0,8.0,9.0,10.0,10.8]:
    for i in range(72):
        x,y = CX+radius*math.cos(i*2*math.pi/72), CY+radius*math.sin(i*2*math.pi/72)
        hit, point, normal, index = arm.ray_cast(Vector((x,y,FLOOR+0.0001)), Vector((0,0,1)))
        assert hit
        thicknesses.append(point.z-FLOOR)
assert min(thicknesses) >= 1.49, min(thicknesses)
exported = export(arm, 'base-2_MG90S-clearance-D22-depth6.5_trial.stl')

# Retain the complete underside mating surface, omitting the tall upper bracket.
coupon = arm.copy()
coupon.data = arm.data.copy()
bpy.context.collection.objects.link(coupon)
coupon.name = 'Underside clearance fit test - not a structural replacement'
bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,-20))
clip = bpy.context.object
clip.dimensions = (60,60,30.5)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
boolean(coupon, clip, 'INTERSECT')
bpy.data.objects.remove(clip, do_unlink=True)
coupon_report = export(coupon, 'base-2_MG90S-clearance_fit-test.stl')
coupon.hide_render = True
coupon.hide_set(True)
cutter.hide_render = True
cutter.hide_set(True)
original.hide_render = True
original.hide_set(True)

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = 'MILLIMETERS'
scene.render.engine = 'CYCLES'
scene.cycles.samples = 24
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.world.color = (0.45,0.45,0.45)
mat = bpy.data.materials.new('Orange plastic')
mat.use_nodes = True
mat.diffuse_color = (0.7,0.16,0.025,1)
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.7,0.16,0.025,1)
for obj in [arm,original]:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.material_index = 0
target = Vector((0,0,-9))
bpy.ops.object.camera_add(location=(0,28,-85))
camera = bpy.context.object
camera.rotation_euler = (target-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 48
scene.camera = camera
bpy.ops.object.light_add(type='AREA', location=(-25,-20,-60))
light = bpy.context.object
light.data.energy = 20000
light.data.size = 45
light.rotation_euler = (target-light.location).to_track_quat('-Z','Y').to_euler()
for name,obj in [('before',original),('after',arm)]:
    original.hide_render = obj != original
    arm.hide_render = obj != arm
    scene.render.filepath = str(OUT / ('base-2_clearance_'+name+'.png'))
    bpy.ops.render.render(write_still=True)
original.hide_render = True
arm.hide_render = False
select(arm)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_location = target
            area.spaces.active.region_3d.view_distance = 75
            area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'base-2_MG90S-clearance_trial.blend'))
result = {
    'source': str(SOURCE), 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'status': 'Unmeasured fit trial, not physically verified',
    'recess_diameter_before_mm':20, 'recess_diameter_after_mm':22,
    'recess_depth_before_mm':6, 'recess_depth_after_mm':6.5,
    'mouth_chamfer_mm':0.3, 'center_hole_diameter_mm_unchanged':7.5,
    'upper_vertices_preserved':len(upper),
    'sampled_min_roof_thickness_mm':min(thicknesses), 'thickness_sample_count':len(thicknesses),
    'original':before, 'modified':after, 'exported_stl':exported, 'fit_test_stl':coupon_report,
}
(OUT / 'base-2_clearance-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
