"""Reproducible, illustrative assembly using the user's actual STL meshes.

Blender --background --python-exit-code 1 --python build_assembly.py
The original meshes and camera-mount production file are never overwritten.
Servo/PCB/lens/wiring are display proxies, not dimensioned manufacturing CAD.
"""
from pathlib import Path
import bpy
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view
import math
import json
import hashlib
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
SCALE = 0.001
FPS, END = 24, 576
PARTS, GROUPS, SOURCES = [], {}, {}
R = lambda angle, axis: Matrix.Rotation(math.radians(angle), 4, axis)
T = lambda xyz: Matrix.Translation(Vector(xyz))


def mat(name, color, metallic=0, roughness=.38):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metallic
    p.inputs['Roughness'].default_value = roughness
    return m


def group(name, offset, start, finish):
    g = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(g)
    g.parent = MODEL
    g.empty_display_size = 4
    for frame, loc in ((1, offset), (start, offset), (finish, (0,0,0)), (END,(0,0,0))):
        g.location = loc
        g.keyframe_insert('location', frame=frame)
    GROUPS[name] = {'object': g, 'offset_mm': offset, 'frames': [start,finish]}
    return g


def register(obj, name, material, parent, source=None, proxy=False):
    obj.name = name
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj.parent = parent
    obj['is_visual_proxy'] = proxy
    if source:
        obj['source_mesh'] = str(source.relative_to(ROOT))
    PARTS.append(obj)
    return obj


def mesh(file, name, material, parent, matrix=None):
    path = ROOT / file
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.object
    obj.matrix_world = matrix or Matrix.Identity(4)
    register(obj, name, material, parent, path)
    SOURCES[file] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Preserve the source mesh topology; render-only normal smoothing.
    for p in obj.data.polygons:
        p.use_smooth = False
    return obj


def box(name, size, position, material, parent, rotation=None, bevel=.3, proxy=True):
    bpy.ops.mesh.primitive_cube_add(location=position)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if rotation:
        obj.rotation_euler = rotation.to_euler()
    if bevel:
        m=obj.modifiers.new('visual edge softness','BEVEL');m.width=bevel;m.segments=3
    register(obj,name,material,parent,proxy=proxy)
    return obj


def cyl(name, radius, depth, position, material, parent, rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=radius,depth=depth,location=position)
    obj=bpy.context.object
    if rotation: obj.rotation_euler=rotation.to_euler()
    register(obj,name,material,parent,proxy=True)
    b=obj.modifiers.new('soft metal edge','BEVEL');b.width=.15;b.segments=2
    return obj


def at(matrix, xyz):
    return matrix @ Vector(xyz)


def proxy_box(name,size,loc,material,parent,matrix,bevel=.3):
    return box(name,size,at(matrix,loc),material,parent,matrix.to_3x3(),bevel)


def servo(name, matrix, parent):
    # Reference origin = output shaft axis; local +Z faces out of the servo.
    proxy_box(name+' / body',(12,23,22),(0,-5.5,-13.5),BLACK,parent,matrix,.9)
    proxy_box(name+' / mounting ears',(12,32,2.2),(0,-5.5,-5),BLACK,parent,matrix,.5)
    cyl(name+' / gearbox cap',5.5,3,at(matrix,(0,0,-2.5)),BLACK,parent,matrix.to_3x3())
    cyl(name+' / shaft',2.4,4,at(matrix,(0,0,1)),METAL,parent,matrix.to_3x3())
    cyl(name+' / horn',5.3,1.7,at(matrix,(0,0,3)),BLACK,parent,matrix.to_3x3())
    proxy_box(name+' / identification stripe',(10,.4,7),(0,-17.15,-14),LABEL,parent,matrix,.1)


def wire(name, points, color, parent, radius=.55):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D'
    curve.resolution_u=12;curve.bevel_depth=radius;curve.bevel_resolution=3
    s=curve.splines.new('BEZIER');s.bezier_points.add(len(points)-1)
    for b,p in zip(s.bezier_points,points):
        b.co=p;b.handle_left_type='AUTO';b.handle_right_type='AUTO'
    o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o)
    register(o,name,color,parent,proxy=True)
    return o


def pose(pivot, target, rot):
    return T(target) @ rot @ T(-Vector(pivot))


def axis_matrix(x,y,z):
    return Matrix((x,y,z)).transposed().to_4x4()


def create_robot():
    base=group('01_Base_and_electronics',(0,0,0),1,1)
    shell=group('02_Lower_case',(0,0,18),49,80)
    plate=group('03_Base_plate',(0,0,38),75,108)
    yaw=group('04_Rotation_base',(-60,0,65),121,156)
    shoulder=group('05_Shoulder_and_upper_arm',(-88,0,74),165,204)
    forearm=group('06_Forearm',(68,-12,55),217,252)
    claw=group('07_Gripper',(55,-50,40),267,305)
    mast=group('08_New_camera_mount',(82,26,10),313,348)
    camera=group('09_Sense_and_camera',(78,18,70),357,394)
    cables=group('10_Cable_route',(0,0,0),399,408)

    # Printed box shell coordinates match the original PDF assembly.
    mesh('case_lid.stl','底盖 / original case lid',CHARCOAL,base)
    mesh('case.stl','底部电子盒 / original case',CHARCOAL,shell,T((0,0,.605)))
    mesh('base_breadboard.stl','底板与后电子舱 / original base',ORANGE,plate)
    center=Vector((2.9,108.5,-3.255))
    mesh('base1.stl','底座圆筒 / base1',ORANGE,yaw,T(center))
    base2matrix=T(center+Vector((0,0,39.25)))
    mesh('base-2.stl','回转肩座 / base-2',ORANGE,shoulder,base2matrix)
    servo('M1 回转舵机',T(center+Vector((0,0,20))),yaw)

    # Shoulder shaft points to -X so the long upper arm sits to the side.
    shoulder_axis=center+Vector((-9,-5.5,47.75))
    Srot=axis_matrix((0,0,-1),(0,-1,0),(-1,0,0))
    servo('M2 大臂舵机',T(shoulder_axis)@Srot,shoulder)
    d1=Vector((0,-math.cos(math.radians(57)),math.sin(math.radians(57))))
    shaft=Vector((-1,0,0))
    a1rot=axis_matrix(d1.cross(shaft),d1,shaft)
    a1=pose((0,-34,3),shoulder_axis+Vector((-5,0,0)),a1rot)
    mesh('舵盘槽调整/arm-1_slot-plus-0.4mm.stl','大臂 / arm-1 slot-adjusted',ORANGE,shoulder,a1)
    elbow=at(a1,(0,29.525,3))
    servo('M3 小臂舵机',T(elbow)@a1rot,shoulder)

    d2=Vector((0,-math.cos(math.radians(25)),-math.sin(math.radians(25))))
    a2rot=axis_matrix(shaft,d2,shaft.cross(d2))
    a2=pose((-25,-34,6),elbow+Vector((-5,0,0)),a2rot)
    mesh('舵盘槽调整/arm-2_slot-plus-0.4mm.stl','小臂 / arm-2 slot-adjusted',IVORY,forearm,a2)

    # One servo drives the two printed fingers. Source gripping-gear centres
    # are aligned to the 18.5 mm-spaced pin holes in the real arm_support STL.
    sup=a2@T((27.5,32.025,-3.5))
    mesh('arm_support.stl','夹爪舵机托板 / arm_support',ORANGE,claw,sup)
    servo('M4 夹爪舵机',sup@T((-52.5,-1.73,-4.7))@R(180,'Y'),claw)
    for file,piv,tar,angle in [
        ('gear_arm1.stl',(17.5845,14.0095,0),(-43.25,16,-3.35),-98),
        ('gear_arm2.stl',(17.583,-15.2355,0),(-61.75,16,-3.35),-82)]:
        transform=sup@pose(piv,tar,R(angle,'Z'))
        mesh(file,'夹指 / '+file,ORANGE,claw,transform)
    mesh('gear.stl','夹爪下层同轴大齿轮 / gear',ORANGE,claw,
         sup@pose((55,13.0225,0),(-61.75,16,-8.05),R(-82,'Z')))
    mesh('gear_servo.stl','舵机下层小齿轮 / gear_servo',ORANGE,claw,
         sup@pose((55,-18,0),(-52.5,-1.73,-8.05),R(12,'Z')))
    for x in (-61.75,-43.25):
        cyl('夹爪枢轴螺丝 / schematic',1.6,8,at(sup,(x,16,0)),METAL,claw,sup.to_3x3())

    mesh('摄像头支架改造/xiao_sense_camera_mast_v1.stl','新增后置相机支架 / V1',TEAL,mast)
    # Keep the board + Sense extension together; do not invent a detached
    # high-speed camera ribbon. Lens/stack clearance is illustrative.
    camrot=R(30,'X')@R(90,'X')
    cp=Vector((2.75,197.2,77.5))+R(30,'X').to_3x3()@Vector((0,-2,12.5))
    cm=T(cp)@camrot
    proxy_box('XIAO main board / schematic',(17.8,21,1.1),(0,0,-5.8),PCB,camera,cm,.4)
    proxy_box('Sense extension / schematic',(17.8,21,1.1),(0,0,-2.7),PCB,camera,cm,.4)
    proxy_box('ESP32 shield / schematic',(10,11,1.8),(0,1,-7),METAL,camera,cm,.3)
    proxy_box('Camera sensor body / schematic',(9,9,3.5),(0,0,0),BLACK,camera,cm,.5)
    cyl('Camera lens barrel / schematic',3.3,4,at(cm,(0,0,3.6)),BLACK,camera,cm.to_3x3())
    cyl('Camera optical glass / schematic',2.6,.5,at(cm,(0,0,5.9)),GLASS,camera,cm.to_3x3())
    proxy_box('USB-C port / schematic',(8.8,3.8,3),(0,-10,-6.5),METAL,camera,cm,.5)
    for x in (-7.4,7.4):
        proxy_box('Board pin header / schematic',(1.8,17,3.6),(x,0,-4.2),BLACK,camera,cm,.2)
    # Thin keeper strips are visual stand-ins for small cable ties.
    for y in (-8.3,8.3):
        proxy_box('Retention tie / schematic',(29,1.5,.8),(0,y,1.7),BLACK,camera,cm,.25)

    # Electronics and harness routes deliberately schematic, no wiring claims.
    box('Rear distribution PCB / schematic',(62,30,1.5),(2.75,160,-2.2),PCB,plate,bevel=.6)
    for x in (-16,-5,6,17):
        box('Servo connector / schematic',(6,8,5),(x,162,1),BLACK,plate,bevel=.3)
        for y in (159.5,162,164.5):
            cyl('Pin / schematic',.5,2,(x,y,4),METAL,plate)
    paths=[[(19,162,5),(30,145,12),(27,115,21),list(center+Vector((10,1,12)))],
           [(-5,162,5),(-21,145,20),(-24,115,44),list(shoulder_axis+Vector((16,0,-10)))],
           [(6,162,5),(-28,144,25),(-33,99,60),list(elbow+Vector((15,-3,-12)))],
           [(-16,162,5),(-30,132,30),(-38,86,68),list(at(a2,(-25,20,-8)))]]
    for n,path in enumerate(paths):
        wire('舵机线束示意 '+str(n+1),path,CABLE,cables,.65)
    wire('Camera USB/power routing / schematic',
         [list(at(cm,(0,-12,-6.5))),(8,204,79),(9,205,30),(20,180,7)],CABLE,cables,.9)
    # Reveal harnesses only after rigid components have arrived.
    for ob in [o for o in PARTS if o.parent==cables]:
        ob.hide_render=True;ob.keyframe_insert('hide_render',frame=1)
        ob.hide_render=True;ob.keyframe_insert('hide_render',frame=397)
        ob.hide_render=False;ob.keyframe_insert('hide_render',frame=399)
    # Four base screws are only visible fit placeholders, not a BOM.
    for x in (-14.1,19.9):
        for y in (91.5,125.5):
            cyl('底座紧固件示意',2.2,3,(x,y,2),METAL,yaw)


def camera_at(position,target,scale):
    CAMERA.location=Vector(position)*SCALE
    CAMERA.rotation_euler=(Vector(target)*SCALE-CAMERA.location).to_track_quat('-Z','Y').to_euler()
    CAMERA.data.type='ORTHO';CAMERA.data.ortho_scale=scale*SCALE


def animate_camera():
    # Wide, stable view for the assembly; gentle orbit only after completion.
    aim=bpy.data.objects.new('CAMERA / always look at assembly',None)
    bpy.context.collection.objects.link(aim)
    track=CAMERA.constraints.new('TRACK_TO');track.target=aim
    track.track_axis='TRACK_NEGATIVE_Z';track.up_axis='UP_Y'
    for frame,deg,scale in [(1,0,450),(48,0,450),(408,0,450),(432,0,370),
                            (480,60,370),(528,120,370),(576,180,370)]:
        target=Vector((0,102,67 if frame<=408 else 30))
        initial=Vector((265,-285,185))
        pos=target+R(deg,'Z').to_3x3()@initial
        camera_at(pos,target,scale)
        aim.location=target*SCALE;aim.keyframe_insert('location',frame=frame)
        CAMERA.keyframe_insert('location',frame=frame)
        CAMERA.data.keyframe_insert('ortho_scale',frame=frame)


def scene_setup():
    global MODEL,CAMERA,ORANGE,TEAL,IVORY,BLACK,METAL,LABEL,PCB,GLASS,CABLE,CHARCOAL
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    MODEL=bpy.data.objects.new('ASSEMBLY / millimetres scaled to metres',None)
    bpy.context.collection.objects.link(MODEL);MODEL.scale=(SCALE,)*3
    ORANGE=mat('01 Original printed orange',(.82,.22,.045))
    TEAL=mat('02 New camera mount teal',(.025,.40,.37))
    IVORY=mat('03 Existing light forearm',(.77,.79,.75))
    BLACK=mat('04 Servo charcoal',(.045,.055,.070),.15,.32)
    CHARCOAL=mat('05 Lower electronics enclosure',(.12,.15,.18))
    METAL=mat('06 Metal pins',(.63,.65,.67),.78,.25)
    LABEL=mat('07 Servo label',(.42,.035,.035))
    PCB=mat('08 PCB green',(.045,.21,.14))
    GLASS=mat('09 Lens glass',(.018,.055,.095),.5,.13)
    CABLE=mat('10 Cable dark',(.045,.04,.035))
    create_robot()
    bpy.ops.mesh.primitive_plane_add(size=2000*SCALE,location=(0,100*SCALE,-32.15*SCALE))
    floor=bpy.context.object;floor.name='STUDIO / floor'
    floor.data.materials.append(mat('Warm paper studio',(.72,.71,.67),0,.8))
    bpy.ops.object.camera_add();CAMERA=bpy.context.object;CAMERA.name='CAMERA / assembly and orbit'
    bpy.context.scene.camera=CAMERA
    CAMERA.data.clip_start=.001;CAMERA.data.clip_end=20
    animate_camera()
    for loc,power,size in [((160,-100,400),2.5,260),((-230,90,260),1.8,230),((50,330,260),3,180)]:
        bpy.ops.object.light_add(type='AREA',location=Vector(loc)*SCALE)
        light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size*SCALE
        light.rotation_euler=(Vector((0,100,50))*SCALE-light.location).to_track_quat('-Z','Y').to_euler()
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC';scene.unit_settings.length_unit='MILLIMETERS'
    scene.frame_start=1;scene.frame_end=END;scene.render.fps=FPS
    scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.world.color=(.72,.71,.67)
    scene.view_settings.view_transform='AgX'
    scene.render.film_transparent=False
    scene.render.engine='BLENDER_WORKBENCH'
    sh=scene.display.shading;sh.light='STUDIO';sh.studio_light='paint.sl'
    sh.color_type='MATERIAL';sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH'
    sh.curvature_ridge_factor=1.1;sh.curvature_valley_factor=1.0;sh.show_specular_highlight=True
    sh.background_type='WORLD'
    # Make the saved native file open at a useful assembled pose.
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_distance=.36
            area.spaces.active.region_3d.view_location=Vector((0,.11,.045))
            area.spaces.active.clip_start=.001


def render_still(name,frame,position,target,scale):
    scene=bpy.context.scene;scene.frame_set(frame)
    # Render refresh reevaluates animated cameras; use an unanimated copy.
    still=CAMERA.copy();still.data=CAMERA.data.copy()
    still.animation_data_clear();still.data.animation_data_clear()
    for constraint in list(still.constraints):
        still.constraints.remove(constraint)
    bpy.context.collection.objects.link(still)
    still.location=Vector(position)*SCALE
    still.rotation_euler=(Vector(target)*SCALE-still.location).to_track_quat('-Z','Y').to_euler()
    still.data.ortho_scale=scale*SCALE;scene.camera=still
    scene.render.filepath=str(OUT/name)
    bpy.ops.render.render(write_still=True)
    scene.camera=CAMERA;bpy.data.objects.remove(still,do_unlink=True)


def save_manifest():
    scene=bpy.context.scene;scene.frame_set(432);bpy.context.view_layer.update()
    items=[]
    for ob in PARTS:
        items.append({'name':ob.name,'visual_proxy':bool(ob.get('is_visual_proxy',False)),
            'source':ob.get('source_mesh',None),'group':ob.parent.name,
            'matrix_local_mm':[list(row) for row in ob.matrix_local]})
    checks={key:hashlib.sha256((ROOT/key).read_bytes()).hexdigest()==sha for key,sha in SOURCES.items()}
    assert all(checks.values())
    manifest={'type':'illustrative_assembly_not_manufacturing_validation','source_hashes':SOURCES,
        'source_files_unchanged':checks,'scene_scale_m_per_mm':SCALE,'objects':items,
        'animation':{'fps':FPS,'frames':END,'duration_seconds':24,
            'chapters_seconds':[0,2,5,9,13,17],
            'groups':{k:{'offset_mm':v['offset_mm'],'assembly_frames':v['frames']} for k,v in GROUPS.items()}},
        'geometric_basis':{'base_hole_center_mm':[2.9,108.5],'base_hole_pitch_mm':34,
            'upper_arm_local_pivot':[0,-34,3],'forearm_local_pivot':[-25,-34,6],
            'gripper_pin_pitch_mm':18.5,'camera_mast_pose':'unchanged source coordinates'},
        'omitted_alternatives':['tapa-v2.stl duplicates base-2 geometry'],
        'gripper_transmission':'lower 8-tooth servo gear drives 12-tooth gear coaxial with one finger; upper fingers mesh. Tooth phase illustrative, not collision-certified.',
        'limitations':['servo spline offsets and fasteners illustrative','not a joint motion/control simulation',
            'no full-robot collision, print fit or real lens field-of-view validation',
            'XIAO Sense board, camera, cabling and servo housings are schematic proxies',
            'open camera holder uses provisional tie/stack placement; do not print hardware proxies'],
        'credits':{'original_remix':'Arun Kumar - Robotic Arm with a base for components (1596575)',
            'original_arm':'RACBOTS - Brazo Robotico','printed_mesh_license':'CC BY-SA 4.0 per bundled original PDF'}}
    (OUT/'assembly_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


def check_animation_framing():
    scene=bpy.context.scene
    failing=[]
    extrema=[1,1,0,0]
    for frame in range(1,END+1):
        scene.frame_set(frame);bpy.context.view_layer.update()
        coords=[world_to_camera_view(scene,CAMERA,ob.matrix_world@Vector(corner))
                for ob in PARTS if not ob.hide_render for corner in ob.bound_box]
        bounds=[min(p.x for p in coords),min(p.y for p in coords),
                max(p.x for p in coords),max(p.y for p in coords)]
        extrema=[min(extrema[0],bounds[0]),min(extrema[1],bounds[1]),
                 max(extrema[2],bounds[2]),max(extrema[3],bounds[3])]
        if bounds[0]<.015 or bounds[1]<.015 or bounds[2]>.985 or bounds[3]>.985:
            failing.append({'frame':frame,'bounds':bounds})
    report={'tested_frames':END,'bounding_box_screen_extrema':extrema,'clipped_frames':failing,
            'scope':'projected object bounding boxes, excludes studio floor and hidden harnesses'}
    (OUT/'framing_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert not failing, 'Frame clipping: '+str(failing[:3])
    scene.frame_set(432)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    scene_setup();save_manifest()
    scene=bpy.context.scene
    scene.render.engine='BLENDER_EEVEE'
    render_still('assembled_hero.png',432,(255,-215,175),(0,100,36),318)
    render_still('exploded.png',1,(280,-230,220),(0,104,75),455)
    render_still('assembled_side.png',432,(320,82,73),(0,82,38),328)
    render_still('camera_detail.png',432,(92,89,124),(2.75,190,82),93)
    scene.render.engine='BLENDER_WORKBENCH'
    scene.frame_set(432)
    scene.render.resolution_x=1280;scene.render.resolution_y=800
    check_animation_framing()
    scene.render.filepath=str(OUT/'frames'/'frame_')
    (OUT/'frames').mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'robot_arm_camera_assembly.blend'))
    print('ASSEMBLY_BUILD_OK',len(PARTS),'objects;',len(SOURCES),'source meshes')
    if '--render-animation' in sys.argv:
        bpy.ops.render.render(animation=True)


if __name__=='__main__':
    main()
