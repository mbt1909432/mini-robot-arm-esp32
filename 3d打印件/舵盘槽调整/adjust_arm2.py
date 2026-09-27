"""Apply the verified arm-1 pocket cutter to the side-facing arm-2 pocket."""
from pathlib import Path
import hashlib
import json

import bpy
import bmesh
from mathutils import Matrix, Vector

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'arm-2.stl'
FRAME = Matrix(((0, 0, 1, -27.5), (0, 1, 0, 0), (-1, 0, 0, 6), (0, 0, 0, 1)))


def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def boolean(obj, cutter, operation='DIFFERENCE'):
    select_only(obj)
    mod = obj.modifiers.new('Pocket adjustment', 'BOOLEAN')
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


def inspect(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    pending = set(bm.verts)
    components = 0
    while pending:
        stack = [pending.pop()]
        components += 1
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                other = e.other_vert(v)
                if other in pending:
                    pending.remove(other)
                    stack.append(other)
    result = {
        'vertices': len(bm.verts), 'faces': len(bm.faces),
        'non_manifold_edges': sum(not e.is_manifold for e in bm.edges),
        'inconsistent_edges': sum(not e.is_contiguous for e in bm.edges),
        'degenerate_faces': sum(f.calc_area() < 1e-9 for f in bm.faces),
        'connected_components': components,
        'volume_mm3': bm.calc_volume(signed=True),
        'bounds_mm': [[min(v.co[i] for v in bm.verts), max(v.co[i] for v in bm.verts)] for i in range(3)],
    }
    bm.free()
    return result


def require_solid(report):
    for key in ['non_manifold_edges', 'inconsistent_edges', 'degenerate_faces']:
        assert report[key] == 0, report
    assert report['connected_components'] == 1, report
    assert report['volume_mm3'] > 0, report


def export_verify(obj, filename):
    select_only(obj)
    path = OUT / filename
    bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True, apply_modifiers=True)
    bpy.ops.wm.stl_import(filepath=str(path))
    imported = bpy.context.object
    report = inspect(imported)
    require_solid(report)
    assert abs(report['volume_mm3'] - inspect(obj)['volume_mm3']) < 0.001
    bpy.data.objects.remove(imported, do_unlink=True)
    return report


bpy.ops.wm.open_mainfile(filepath=str(OUT / 'arm-1_slot-adjusted.blend'))
cutter = bpy.data.objects['Pocket clearance cutter']
reference = bpy.data.objects['Original arm-1 - reference']
reference_points = [v.co.copy() for v in reference.data.vertices if v.co.y < -15 and abs(v.co.z-3) < 1e-5]
assert len(reference_points) == 35
# Keep the exact same cutter and viewing setup, rotated into arm-2 coordinates.
for obj in list(bpy.data.objects):
    if obj == cutter or obj.type in {'CAMERA', 'LIGHT'}:
        obj.matrix_world = FRAME @ obj.matrix_world
    else:
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.wm.stl_import(filepath=str(SOURCE))
arm = bpy.context.object
arm.name = 'arm-2 - pocket clearance 0.4mm per side'
original = arm.copy()
original.data = arm.data.copy()
bpy.context.collection.objects.link(original)
original.name = 'Original arm-2 - reference'
original.hide_set(True)
original.hide_render = True
before = inspect(arm)
require_solid(before)
inverse = FRAME.inverted()
local_points = [inverse @ v.co for v in arm.data.vertices]
pocket_floor = [p for p in local_points if p.y < -15 and abs(p.z-3) < 1e-5]
assert len(pocket_floor) == 35
max_profile_error = max(min((p-q).length for q in pocket_floor) for p in reference_points)
assert max_profile_error < 1e-4, max_profile_error
boolean(arm, cutter)
after = inspect(arm)
require_solid(after)
assert before['bounds_mm'] == after['bounds_mm']
removed_volume = before['volume_mm3'] - after['volume_mm3']
assert 50 < removed_volume < 75, removed_volume

outside = [v.co.copy() for v in original.data.vertices
           if (inverse @ v.co).y > -15 or (inverse @ v.co).z < 2.79 or abs((inverse @ v.co).x) > 4.2]
modified_points = [v.co.copy() for v in arm.data.vertices]
assert all(min((p-q).length for q in modified_points) < 1e-5 for p in outside)
exported = export_verify(arm, 'arm-2_slot-plus-0.4mm.stl')

coupon = arm.copy()
coupon.data = arm.data.copy()
bpy.context.collection.objects.link(coupon)
coupon.name = 'arm-2 fit test'
bpy.ops.mesh.primitive_cube_add(size=1, location=(-25, -30, 6))
clip = bpy.context.object
clip.dimensions = (30, 32, 30)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
boolean(coupon, clip, 'INTERSECT')
bpy.data.objects.remove(clip, do_unlink=True)
coupon_report = export_verify(coupon, 'arm-2_fit-test.stl')
coupon.hide_set(True)
coupon.hide_render = True

mat = bpy.data.materials.new('arm-2 orange plastic')
mat.diffuse_color = (0.8, 0.2, 0.025, 1)
mat.use_nodes = True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.55, 0.11, 0.012, 1)
mat.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = 0.6
for obj in [arm, original]:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.material_index = 0
scene = bpy.context.scene
for name, model in [('before', original), ('after', arm)]:
    original.hide_render = model != original
    arm.hide_render = model != arm
    scene.render.filepath = str(OUT / ('arm-2_pocket_' + name + '.png'))
    bpy.ops.render.render(write_still=True)
original.hide_render = True
arm.hide_render = False
select_only(arm)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            region = area.spaces.active.region_3d
            region.view_location = Vector((-25, 0, 6))
            region.view_distance = 100
            region.view_rotation = scene.camera.rotation_euler.to_quaternion()
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = 'MILLIMETERS'
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'arm-2_slot-adjusted.blend'))
report = {
    'source': str(SOURCE),
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'blender_version': bpy.app.version_string,
    'units': 'millimeters, original STL orientation and scale preserved',
    'pocket_side_clearance_mm': 0.4,
    'pocket_depth_before_mm': 2.0, 'pocket_depth_after_mm': 2.2,
    'entry_chamfer_mm': 0.2,
    'round_recess_diameter_nominal_mm': 7.8,
    'round_through_hole_diameter_mm': 7.0,
    'remaining_floor_thickness_mm': 2.8,
    'rim_minimum_nominal_mm': 1.9,
    'original_pocket_match_to_arm1_max_error_mm': max_profile_error,
    'outside_pocket_vertices_preserved': len(outside),
    'removed_volume_mm3': removed_volume,
    'original': before, 'modified': after, 'exported_stl': exported,
    'coupon_exported_stl': coupon_report, 'physical_fit_verified': False,
}
(OUT / 'arm-2_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('VALIDATION', json.dumps(report, indent=2))
