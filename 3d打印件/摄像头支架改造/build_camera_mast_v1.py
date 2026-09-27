"""Build a detachable rear-wall camera mast for the mini robot arm.

The mount is deliberately separate from the original arm parts. It clips over
the rear wall of base_breadboard.stl and leaves the servo geometry untouched.
Dimensions are a V1 fit-test; confirm the real board, camera and wall before
printing a final enclosure.
"""

from pathlib import Path
import json
import math
import hashlib

import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree


OUT = Path(__file__).resolve().parent
MODEL_ROOT = OUT.parent
BASE_BREADBOARD = MODEL_ROOT / "base_breadboard.stl"
BLEND_OUT = OUT / "xiao_sense_camera_mast_v1.blend"
STL_OUT = OUT / "xiao_sense_camera_mast_v1.stl"
PREVIEW_OUT = OUT / "xiao_sense_camera_mast_v1_preview.png"
VALIDATION_OUT = OUT / "validation.json"

MOUNT_PREFIX = "CAM_MOUNT_"
MOUNT_OBJECTS = []
CAMERA_TILT_DEG = 30.0
STL_CHECK = {}


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    # Materials are created at module load time. Do not purge them here before
    # the freshly built objects have had a chance to reference them.
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def material(name, color, metallic=0.0, roughness=0.48):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


ORANGE = material("Original orange base", (0.86, 0.16, 0.035), roughness=0.42)
TEAL = material("Camera mount test teal", (0.035, 0.44, 0.42), roughness=0.36)
BLACK = material("Camera board placeholder", (0.025, 0.03, 0.035), roughness=0.28)
FLOOR_MAT = material("Floor", (0.83, 0.85, 0.88), roughness=0.72)


def finish(obj, bevel=0.65, mat=TEAL):
    obj.name = MOUNT_PREFIX + obj.name
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("small print-friendly edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    MOUNT_OBJECTS.append(obj)
    return obj


def box(name, size, location, bevel=0.65, mat=TEAL):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, bevel=bevel, mat=mat)


def cylinder(name, radius, depth, location, rotation=(0.0, 0.0, 0.0), vertices=48, mat=TEAL):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=location, rotation=rotation)
    return finish(bpy.context.object, bevel=0.0, mat=mat)


def cut_cylinder(target, location, radius, depth, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth,
                                       location=location, rotation=rotation)
    cutter = bpy.context.object
    modifier = target.modifiers.new("through hole", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def import_stl(path, mat):
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.data.materials.append(mat)
    return obj


def build_mount():
    # base_breadboard's rear wall is approximately x=-12..18, y=190.6..194.6,
    # top z=13.75 in the source coordinate system. The clamp intentionally
    # leaves about 1-2 mm of clearance for a first fit test.
    clamp_width = 54.0
    clamp_z = 7.8
    jaw = box("rear clamp front jaw", (clamp_width, 3.2, 17.0), (2.75, 188.5, clamp_z), 0.55)
    # Rear-wall ribs protrude farther forward than the nominal wall plane.
    # Cut their actual outline into the jaw with 0.3 mm fore/aft clearance.
    # This affects only our new part; the source base is never overwritten.
    bpy.ops.wm.stl_import(filepath=str(BASE_BREADBOARD))
    cutter = bpy.context.object
    cutter.location.y -= 0.3
    modifier = jaw.modifiers.new("rear wall rib relief", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = jaw
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    box("rear clamp back jaw", (clamp_width, 3.2, 17.0), (2.75, 198.8, clamp_z), 0.55)
    box("rear clamp top bridge", (clamp_width - 0.4, 13.5, 3.2), (2.75, 193.65, 16.5), 0.55)

    # A stiff rear mast keeps the camera out of the rotating base envelope.
    box("rear mast", (42.0, 5.0, 61.0), (2.75, 201.2, 47.0), 0.8)
    box("left mast gusset", (12.0, 9.0, 8.0), (-12.0, 198.7, 19.0), 0.8)
    box("right mast gusset", (12.0, 9.0, 8.0), (17.5, 198.7, 19.0), 0.8)
    box("tilted frame support", (34.0, 7.0, 6.0), (2.75, 200.5, 75.8), 0.45)

    # Generic vertical camera-board cradle. The center window is intentionally
    # generous; the actual camera/board dimensions will be tightened in V2.
    frame_y = 197.2
    frame_z = 90.0
    first_frame_part = len(MOUNT_OBJECTS)
    frame = box("camera frame", (38.0, 8.0, 29.0), (2.75, frame_y, frame_z), 0.55)
    bpy.ops.mesh.primitive_cube_add(location=(2.75, frame_y, frame_z))
    cutter = bpy.context.object
    cutter.dimensions = (26.0, 20.0, 21.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    modifier = frame.modifiers.new("open optical window", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = frame
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)

    # A small lower tray supports a camera board or FPC camera module. The
    # tray is open on the front so the lens can look toward the work area.
    box("camera lower tray", (38.0, 12.0, 3.0), (2.75, 194.6, 75.0), 0.45)

    # Two vertical strap holes in the lower side rails accept a small zip tie
    # or M2/M3 strap while the board size is still being verified.
    for x in (-13.25, 18.75):
        for z in (84.0, 96.0):
            cut_cylinder(frame, (x, frame_y, z), 1.55, 12.0,
                         rotation=(math.radians(90), 0.0, 0.0))

    # Rotate only the camera cradle: front normal (0,-1,0) now points down
    # toward the work area. Keep the mast below the optical window and holes.
    pivot = Vector((2.75, frame_y, 77.5))
    tilt = (Matrix.Translation(pivot)
            @ Matrix.Rotation(math.radians(CAMERA_TILT_DEG), 4, "X")
            @ Matrix.Translation(-pivot))
    for obj in MOUNT_OBJECTS[first_frame_part:]:
        obj.matrix_world = tilt @ obj.matrix_world
    bpy.context.view_layer.update()


def add_preview_scene():
    # Import the original electronic base only for visual context. It is not
    # selected for STL export and remains unchanged.
    base = import_stl(BASE_BREADBOARD, ORANGE)
    base.name = "REFERENCE_base_breadboard_original"

    bpy.ops.mesh.primitive_plane_add(size=520, location=(0.0, 130.0, -7.0))
    floor = bpy.context.object
    floor.name = "preview floor"
    floor.data.materials.append(FLOOR_MAT)

    bpy.ops.object.camera_add(location=(185.0, 20.0, 155.0))
    camera = bpy.context.object
    target = Vector((2.0, 150.0, 42.0))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 190.0
    camera.data.lens = 46
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(60.0, 85.0, 190.0))
    key = bpy.context.object
    key.data.energy = 950.0
    key.data.shape = "DISK"
    key.data.size = 100.0
    key.rotation_euler = (Vector((0.0, 145.0, 25.0)) - key.location).to_track_quat("-Z", "Y").to_euler()

    bpy.ops.object.light_add(type="AREA", location=(-120.0, 150.0, 70.0))
    fill = bpy.context.object
    fill.data.energy = 500.0
    fill.data.size = 80.0
    fill.rotation_euler = (Vector((0.0, 150.0, 40.0)) - fill.location).to_track_quat("-Z", "Y").to_euler()

    scene = bpy.context.scene
    # Studio lighting avoids physical-light falloff in a millimetre mesh.
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.studiolight_rotate_z = math.radians(25)
    shading.color_type = "MATERIAL"
    shading.background_type = "WORLD"
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.show_specular_highlight = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW_OUT)
    scene.world.color = (0.83, 0.85, 0.88)
    scene.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


def object_bounds(objects):
    points = []
    for obj in objects:
        points.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
    mins = [min(point[i] for point in points) for i in range(3)]
    maxs = [max(point[i] for point in points) for i in range(3)]
    return {"min": mins, "max": maxs, "size": [maxs[i] - mins[i] for i in range(3)]}


def export_mount():
    # The parts intentionally overlap at the joints. Fuse them before STL
    # export so slicers receive one watertight solid instead of overlapping
    # shells. The source arm remains a separate reference object.
    base = MOUNT_OBJECTS[0]
    for other in list(MOUNT_OBJECTS[1:]):
        bpy.ops.object.select_all(action="DESELECT")
        base.select_set(True)
        bpy.context.view_layer.objects.active = base
        modifier = base.modifiers.new("fuse mount part", "BOOLEAN")
        modifier.operation = "UNION"
        modifier.solver = "EXACT"
        modifier.object = other
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(other, do_unlink=True)
    MOUNT_OBJECTS[:] = [base]

    bpy.ops.object.select_all(action="DESELECT")
    base.select_set(True)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # Boolean intersections can leave nearly coincident vertices at a seam.
    # Merge only sub-millimetre duplicates so the printed dimensions remain
    # unchanged while the exported shell becomes cleaner.
    bm = bmesh.new()
    bm.from_mesh(base.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.001)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(base.data)
    bm.free()
    base.data.update()

    bpy.ops.object.select_all(action="DESELECT")
    base.select_set(True)
    bpy.context.view_layer.objects.active = base
    bpy.ops.wm.stl_export(filepath=str(STL_OUT), export_selected_objects=True)


def verify_export():
    """Validate the actual exported triangles, not just the source objects."""
    bpy.ops.wm.stl_import(filepath=str(STL_OUT))
    obj = bpy.context.object
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    unseen = set(bm.verts)
    components = 0
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            vertex = stack.pop()
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in unseen:
                    unseen.remove(other)
                    stack.append(other)
    STL_CHECK.update({
        "vertices": len(bm.verts),
        "triangles": len(bm.faces),
        "connected_components": components,
        "non_manifold_edges": sum(not e.is_manifold for e in bm.edges),
        "zero_length_edges": sum(e.calc_length() < 1e-6 for e in bm.edges),
        "zero_area_faces": sum(f.calc_area() < 1e-9 for f in bm.faces),
        "signed_volume_mm3": bm.calc_volume(signed=True),
        "dimensions_mm": [round(v, 4) for v in obj.dimensions],
    })
    tree = BVHTree.FromBMesh(bm)
    rotation = Matrix.Rotation(math.radians(CAMERA_TILT_DEG), 3, "X")
    pivot = Vector((2.75, 197.2, 77.5))
    direction = rotation @ Vector((0, 1, 0))
    samples = [(x, z) for x in (-9.25, 2.75, 14.75) for z in (80.5, 90.0, 99.5)]
    for x in (-13.25, 18.75):
        for z in (84.0, 96.0):
            samples.append((x, z))
            for k in range(8):
                samples.append((x + 1.2 * math.cos(k * math.pi / 4),
                                z + 1.2 * math.sin(k * math.pi / 4)))
    blocked = 0
    for x, z in samples:
        center = pivot + rotation @ (Vector((x, 197.2, z)) - pivot)
        for sign in (-1, 1):
            hit, _, _, _ = tree.ray_cast(center - direction * 30 * sign,
                                         direction * sign, 60)
            blocked += hit is not None
    STL_CHECK["opening_ray_tests"] = {"rays": len(samples) * 2, "blocked": blocked,
        "scope": "sampled window and four strap holes; not actual camera field of view"}
    bm.free()
    assert STL_CHECK["connected_components"] == 1, STL_CHECK
    assert STL_CHECK["non_manifold_edges"] == 0, STL_CHECK
    assert STL_CHECK["zero_length_edges"] == 0, STL_CHECK
    assert STL_CHECK["zero_area_faces"] == 0, STL_CHECK
    assert STL_CHECK["signed_volume_mm3"] > 0, STL_CHECK
    assert blocked == 0, STL_CHECK

    bpy.ops.wm.stl_import(filepath=str(BASE_BREADBOARD))
    reference = bpy.context.object
    modifier = obj.modifiers.new("nominal base interference check", "BOOLEAN")
    modifier.operation = "INTERSECT"
    modifier.solver = "EXACT"
    modifier.object = reference
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    intersection = {"vertices": len(bm.verts), "faces": len(bm.faces),
                    "volume_mm3": abs(bm.calc_volume()) if bm.faces else 0.0}
    bm.free()
    STL_CHECK["nominal_base_intersection"] = intersection
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.objects.remove(reference, do_unlink=True)
    assert intersection["faces"] == 0, intersection


def save_validation():
    bm = bmesh.new()
    bm.from_mesh(MOUNT_OBJECTS[0].data)
    mesh_quality = {
        "vertices": len(bm.verts),
        "edges": len(bm.edges),
        "polygons": len(bm.faces),
        "non_manifold_edges": sum(1 for edge in bm.edges if not edge.is_manifold),
        "zero_length_edges": sum(1 for edge in bm.edges if (edge.verts[0].co - edge.verts[1].co).length < 1e-6),
    }
    bm.free()
    report = {
        "version": "V1-fit-test",
        "source_reference": "base_breadboard.stl",
        "source_sha256": hashlib.sha256(BASE_BREADBOARD.read_bytes()).hexdigest(),
        "mount_stl": STL_OUT.name,
        "mount_bounds_mm": object_bounds(MOUNT_OBJECTS),
        "rear_wall_assumption_mm": {
            "wall_front_y": 190.6,
            "wall_back_y": 194.6,
            "wall_top_z": 13.75,
            "clearance_note": "V1 clamp uses a generous gap; confirm with the printed base."
        },
        "camera_frame_opening_mm": {"width": 26.0, "height": 21.0},
        "camera_down_tilt_degrees": CAMERA_TILT_DEG,
        "strap_hole_diameter_mm": 3.1,
        "clamp_gap_mm": 7.1,
        "front_jaw_rib_relief": "source base outline shifted forward 0.3 mm; local gap increases at ribs",
        "board_fit": "generic strap cradle; XIAO Sense / camera board dimensions not yet measured",
        "mesh_quality_before_stl_reimport": mesh_quality,
        "stl_reimport_check": STL_CHECK,
        "checks": {
            "source_parts_untouched": True,
            "mount_objects_after_union": len(MOUNT_OBJECTS),
            "stl_exported": STL_OUT.exists(),
            "preview_rendered": PREVIEW_OUT.exists(),
            "physical_print_test": False,
            "physical_camera_fit": False,
            "collision_test_with_full_arm": False
        }
    }
    VALIDATION_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clear_scene()
    build_mount()
    export_mount()
    verify_export()
    add_preview_scene()
    save_validation()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_OUT))
    print(json.dumps({
        "blend": str(BLEND_OUT),
        "stl": str(STL_OUT),
        "preview": str(PREVIEW_OUT),
        "validation": str(VALIDATION_OUT),
        "mount_bounds": object_bounds(MOUNT_OBJECTS),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
