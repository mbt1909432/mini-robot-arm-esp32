"""Run with Blender --background --factory-startup --python adjust_arm1.py."""
from pathlib import Path
import hashlib
import json
import math

import bpy
import bmesh
from mathutils import Vector

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'arm-1.stl'
CLEARANCE = 0.4
EXTRA_DEPTH = 0.2
ENTRY_CHAMFER = 0.2


def mesh_report(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    result = {
        'vertices': len(bm.verts),
        'faces': len(bm.faces),
        'non_manifold_edges': sum(not e.is_manifold for e in bm.edges),
        'inconsistent_edges': sum(not e.is_contiguous for e in bm.edges),
        'degenerate_faces': sum(f.calc_area() < 1e-9 for f in bm.faces),
        'volume_mm3': bm.calc_volume(signed=True),
        'bounds_mm': [[min(v.co[i] for v in bm.verts), max(v.co[i] for v in bm.verts)] for i in range(3)],
    }
    remaining = set(bm.verts)
    components = 0
    while remaining:
        pending = [remaining.pop()]
        components += 1
        while pending:
            for e in pending.pop().link_edges:
                for v in e.verts:
                    if v in remaining:
                        remaining.remove(v)
                        pending.append(v)
    result['connected_components'] = components
    bm.free()
    return result


def pocket_outline(obj):
    # The top rim has one horizontal and one vertical face at each edge.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    rim = []
    for e in bm.edges:
        if not all(abs(v.co.z - 5) < 1e-5 for v in e.verts):
            continue
        normals = [f.normal.z for f in e.link_faces]
        if any(n > 0.99 for n in normals) and any(abs(n) < 0.01 for n in normals):
            rim.append(e)
    seed = next(e for e in rim if all(-20 < v.co.y < -15 and abs(v.co.x) < 3 for v in e.verts))
    adjacency = {}
    for e in rim:
        a, b = e.verts
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    start = seed.verts[0]
    ordered = [start]
    previous, current = start, seed.verts[1]
    while current != start:
        ordered.append(current)
        neighbors = adjacency[current]
        assert len(neighbors) == 2
        previous, current = current, next(v for v in neighbors if v != previous)
    points = [Vector((v.co.x, v.co.y)) for v in ordered]
    bm.free()
    area = sum(a.x*b.y-b.x*a.y for a,b in zip(points, points[1:]+points[:1]))
    if area < 0:
        points.reverse()
    assert min(p.y for p in points) > -38
    assert max(p.y for p in points) < -15
    return points


def offset_polygon(points, distance):
    expanded = []
    for i, p in enumerate(points):
        d1 = (p-points[i-1]).normalized()
        d2 = (points[(i+1) % len(points)]-p).normalized()
        n1 = Vector((d1.y, -d1.x))
        n2 = Vector((d2.y, -d2.x))
        expanded.append(p + (n1+n2) * (distance/(1+n1.dot(n2))))
    return expanded


def make_cutter(points):
    n = len(points)
    inner = offset_polygon(points, CLEARANCE)
    mouth = offset_polygon(points, CLEARANCE + ENTRY_CHAMFER)
    levels = [(inner, 3-EXTRA_DEPTH), (inner, 5-ENTRY_CHAMFER), (mouth, 5), (mouth, 6)]
    verts = [(p.x, p.y, z) for ring,z in levels for p in ring]
    faces = [tuple(reversed(range(n))), tuple(range(3*n,4*n))]
    for level in range(3):
        for i in range(n):
            j = (i+1) % n
            faces.append((level*n+i, level*n+j, (level+1)*n+j, (level+1)*n+i))
    mesh = bpy.data.meshes.new('Pocket cutter mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Pocket clearance cutter', mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def apply_boolean(obj, cutter, operation='DIFFERENCE'):
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new('Local pocket adjustment', 'BOOLEAN')
    modifier.operation = operation
    modifier.solver = 'EXACT'
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def clean_for_stl(obj):
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


bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.wm.stl_import(filepath=str(SOURCE))
arm = bpy.context.object
arm.name = 'arm-1 - pocket clearance 0.4mm per side'
original = arm.copy()
original.data = arm.data.copy()
bpy.context.collection.objects.link(original)
original.name = 'Original arm-1 - reference'
original.hide_render = True
original.hide_set(True)
before = mesh_report(arm)
points = pocket_outline(arm)
cutter = make_cutter(points)
apply_boolean(arm, cutter)
clean_for_stl(arm)
cutter.hide_render = True
cutter.hide_set(True)
after = mesh_report(arm)
assert after['non_manifold_edges'] == 0, after
assert after['inconsistent_edges'] == 0, after
assert after['degenerate_faces'] == 0, after
assert after['connected_components'] == 1, after
assert before['bounds_mm'] == after['bounds_mm']
assert 0 < before['volume_mm3'] - after['volume_mm3'] < 100

# Every original vertex outside the pocket region must remain in the result.
new_points = [v.co.copy() for v in arm.data.vertices]
outside = [v.co.copy() for v in original.data.vertices if v.co.y > -15 or v.co.z < 2.79 or abs(v.co.x) > 4.2]
assert all(any((p-q).length < 1e-5 for q in new_points) for p in outside)

select_only(arm)
full_path = OUT / 'arm-1_slot-plus-0.4mm.stl'
bpy.ops.wm.stl_export(filepath=str(full_path), export_selected_objects=True, apply_modifiers=True)

# A short coupon uses the exact revised geometry, including the full arm thickness.
coupon = arm.copy()
coupon.data = arm.data.copy()
bpy.context.collection.objects.link(coupon)
coupon.name = 'Fit test - print before the full arm'
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -30, 2.5))
clip = bpy.context.object
clip.dimensions = (30, 32, 10)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
apply_boolean(coupon, clip, 'INTERSECT')
clean_for_stl(coupon)
bpy.data.objects.remove(clip, do_unlink=True)
coupon_report = mesh_report(coupon)
assert coupon_report['non_manifold_edges'] == 0
assert coupon_report['connected_components'] == 1
select_only(coupon)
bpy.ops.wm.stl_export(filepath=str(OUT / 'arm-1_fit-test.stl'), export_selected_objects=True, apply_modifiers=True)
coupon.hide_render = True
coupon.hide_set(True)

# Verify the actual exported STL, not only the Blender mesh.
bpy.ops.wm.stl_import(filepath=str(full_path))
reimported = bpy.context.object
exported = mesh_report(reimported)
assert exported['non_manifold_edges'] == 0
assert exported['inconsistent_edges'] == 0
assert exported['degenerate_faces'] == 0
assert exported['connected_components'] == 1
assert abs(exported['volume_mm3']-after['volume_mm3']) < 0.001
bpy.data.objects.remove(reimported, do_unlink=True)
bpy.ops.wm.stl_import(filepath=str(OUT / 'arm-1_fit-test.stl'))
reimported = bpy.context.object
coupon_exported = mesh_report(reimported)
assert coupon_exported['non_manifold_edges'] == 0
assert coupon_exported['inconsistent_edges'] == 0
assert coupon_exported['degenerate_faces'] == 0
assert coupon_exported['connected_components'] == 1
bpy.data.objects.remove(reimported, do_unlink=True)

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = 'MILLIMETERS'
scene.render.engine = 'CYCLES'
scene.cycles.samples = 24
scene.render.resolution_x = 1200
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.world.color = (0.5, 0.5, 0.5)
mat = bpy.data.materials.new('Orange plastic')
mat.diffuse_color = (0.85, 0.24, 0.035, 1)
mat.use_nodes = True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.65, 0.17, 0.025, 1)
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = 0.65
arm.data.materials.append(mat)
original.data.materials.append(mat)
for obj in [arm, original]:
    for polygon in obj.data.polygons:
        polygon.material_index = 0
target = Vector((0, -27, 2.5))
bpy.ops.object.camera_add(location=target + Vector((12, -18, 55)))
camera = bpy.context.object
camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 43
camera.data.clip_end = 1000
scene.camera = camera
for loc, power, size in [((-20,-35,45), 42000, 35), ((20,-10,25), 20000, 25)]:
    bpy.ops.object.light_add(type='AREA', location=loc)
    lamp = bpy.context.object
    lamp.data.energy = power
    lamp.data.size = size
    lamp.rotation_euler = (target-lamp.location).to_track_quat('-Z', 'Y').to_euler()
for name, model in [('before', original), ('after', arm)]:
    original.hide_render = model != original
    arm.hide_render = model != arm
    scene.render.filepath = str(OUT / ('pocket_' + name + '.png'))
    bpy.ops.render.render(write_still=True)
original.hide_render = True
arm.hide_render = False
select_only(arm)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_location = Vector((0, 0, 2.5))
            area.spaces.active.region_3d.view_distance = 100
            area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
            area.spaces.active.clip_end = 10000
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'arm-1_slot-adjusted.blend'))
report = {
    'source': str(SOURCE),
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'blender_version': bpy.app.version_string,
    'units': 'millimeters; STL coordinates are unchanged in scale',
    'pocket_side_clearance_mm': CLEARANCE,
    'pocket_depth_before_mm': 2.0,
    'pocket_depth_after_mm': 2.0+EXTRA_DEPTH,
    'entry_chamfer_mm': ENTRY_CHAMFER,
    'round_recess_diameter_nominal_mm': 7.0+2*CLEARANCE,
    'round_through_hole_diameter_mm': 7.0,
    'tip_recess_width_nominal_mm': 4.5+2*CLEARANCE,
    'rim_minimum_nominal_mm': 6-(3.5+CLEARANCE+ENTRY_CHAMFER),
    'remaining_pocket_floor_mm': 3.0-EXTRA_DEPTH,
    'original': before, 'modified': after, 'exported_stl': exported,
    'coupon': coupon_report,
    'coupon_exported_stl': coupon_exported,
    'outside_pocket_vertices_preserved': len(outside),
    'physical_fit_verified': False,
}
(OUT / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('VALIDATION', json.dumps(report, indent=2))
