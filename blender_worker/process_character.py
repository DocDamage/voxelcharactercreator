from __future__ import annotations
import argparse, json, sys, traceback
from pathlib import Path
import bpy
from mathutils import Vector

ADAPTER_DIR = Path(__file__).resolve().parent / 'adapters'
if str(ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTER_DIR))
from vox_reader import read_vox

def args():
    a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p=argparse.ArgumentParser(); p.add_argument('--job',required=True); p.add_argument('--project-root',required=True); return p.parse_args(a)
def clear(): bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
def rgb(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
def mat(name,color,metal=0.0):
    m=bpy.data.materials.new(name); c=rgb(color); m.diffuse_color=(*c,1); m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF'); b.inputs['Base Color'].default_value=(*c,1); b.inputs['Metallic'].default_value=metal; b.inputs['Roughness'].default_value=.65; return m
def cube(name,loc,scale,m):
    bpy.ops.mesh.primitive_cube_add(location=loc); o=bpy.context.object; o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); o.data.materials.append(m); return o
def rig():
    data=bpy.data.armatures.new('VCF_Rig'); arm=bpy.data.objects.new('VCF_Rig',data); bpy.context.collection.objects.link(arm); bpy.context.view_layer.objects.active=arm; arm.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
    bones={'root':((0,0,0),(0,0,.5)),'pelvis':((0,0,.5),(0,0,1)),'spine':((0,0,1),(0,0,2.5)),'head':((0,0,2.5),(0,0,3.5)),'upper_arm.L':((0,0,2.2),(1.1,0,2.1)),'forearm.L':((1.1,0,2.1),(1.9,0,1.9)),'upper_arm.R':((0,0,2.2),(-1.1,0,2.1)),'forearm.R':((-1.1,0,2.1),(-1.9,0,1.9)),'thigh.L':((.45,0,.8),(.5,0,-.8)),'shin.L':((.5,0,-.8),(.5,0,-2)),'thigh.R':((-.45,0,.8),(-.5,0,-.8)),'shin.R':((-.5,0,-.8),(-.5,0,-2)),'weapon_socket.R':((-1.9,0,1.9),(-2.4,0,1.7))}
    for n,(h,t) in bones.items(): b=data.edit_bones.new(n); b.head=h; b.tail=t
    bpy.ops.object.mode_set(mode='OBJECT'); return arm
def bind(o,arm,bone): o.parent=arm; o.parent_type='BONE'; o.parent_bone=bone; o.matrix_parent_inverse=arm.matrix_world.inverted()
def proxy(job,arm):
    c=job.get('accent_colors') or ['#888','#333','#ddd']; p=mat('Primary',c[0],.15); s=mat('Secondary',c[1] if len(c)>1 else c[0],.2); a=mat('Accent',c[2] if len(c)>2 else c[0],.55); skin=mat('Skin','#D8A175')
    heavy='heavy' in job.get('rig_template','') or job.get('body_template') in ('large_villain','dragoon'); w=1.2 if heavy else .95
    parts=[(cube('torso',(0,0,1.8),(w,.55,.85),p),'spine'),(cube('pelvis',(0,0,.65),(.75,.5,.45),s),'pelvis'),(cube('head',(0,0,3.15),(.72,.62,.68),skin),'head')]
    for side,sgn in [('L',1),('R',-1)]:
        parts += [(cube('upper_arm.'+side,(sgn*1.25,0,2.05),(.42,.42,.7),p),'upper_arm.'+side),(cube('forearm.'+side,(sgn*2,0,1.85),(.36,.36,.65),s),'forearm.'+side),(cube('thigh.'+side,(sgn*.48,0,-.25),(.42,.48,.85),p),'thigh.'+side),(cube('shin.'+side,(sgn*.5,0,-1.55),(.38,.52,.7),s),'shin.'+side)]
    for o,b in parts: bind(o,arm,b)
    if job.get('weapon'):
        prof=job.get('animation_profile',''); name=job['weapon']; scale=(.14,.14,2.45) if ('spear' in name or 'lance' in name) else ((.32,.16,2) if ('buster' in name or 'heavy' in prof) else ((.12,.08,2.7) if ('masamune' in name or 'katana' in prof) else (.18,.1,1.7)))
        o=cube('weapon',(-2.6,0,1),scale,a); bind(o,arm,'weapon_socket.R')
def import_model(p):
    x=p.suffix.lower()
    if x in ('.glb','.gltf'): bpy.ops.import_scene.gltf(filepath=str(p))
    elif x=='.fbx': bpy.ops.import_scene.fbx(filepath=str(p))
    elif x=='.obj': bpy.ops.wm.obj_import(filepath=str(p))
    else: raise ValueError('Unsupported source format. Convert .vox to GLB/OBJ or add the VOX adapter.')
def animate(arm):
    arm.animation_data_create(); act=bpy.data.actions.new('Idle'); arm.animation_data.action=act; bpy.context.view_layer.objects.active=arm; bpy.ops.object.mode_set(mode='POSE')
    for f,v in ((1,-.025),(20,.025),(40,-.025)): b=arm.pose.bones['spine']; b.rotation_mode='XYZ'; b.rotation_euler[1]=v; b.keyframe_insert('rotation_euler',frame=f)
    bpy.ops.object.mode_set(mode='OBJECT'); bpy.context.scene.frame_start=1; bpy.context.scene.frame_end=40
def render_setup(path,res):
    sc=bpy.context.scene; sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=res; sc.render.resolution_y=res; sc.render.resolution_percentage=100; sc.render.film_transparent=True; sc.render.image_settings.file_format='PNG'; sc.render.filepath=str(path)
    bpy.ops.object.camera_add(location=(8.5,-11,5.5)); cam=bpy.context.object; sc.camera=cam; cam.rotation_euler=(Vector((0,0,.7))-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.lens=56
    for loc,energy,size in [((4,-5,8),1200,5),((-4,-2,4),700,4),((0,4,6),900,3)]: bpy.ops.object.light_add(type='AREA',location=loc); l=bpy.context.object; l.data.energy=energy; l.data.size=size
    sc.world.color=(.025,.025,.035)
def main():
    a=args(); root=Path(a.project_root); job=json.loads(Path(a.job).read_text(encoding='utf-8')); slug=job['id']; out=root/'exports'/job['game']/slug.split('_',1)[1]; out.mkdir(parents=True,exist_ok=True); report={'job':slug,'status':'started','checks':{},'warnings':[]}
    try:
        clear(); arm=rig(); src=job.get('source_model')
        if src:
            p=Path(src)
            if not p.exists(): raise FileNotFoundError(p)
            import_model(p); report['checks']['source_imported']=True; report['warnings'].append('Automatic limb classification is not included in this MVP.')
        else: proxy(job,arm); report['checks']['proxy_generated']=True; report['warnings'].append('No source model supplied; generated a pipeline test proxy.')
        animate(arm); preview=out/f'{slug}_preview.png'; render_setup(preview,int(job.get('render_resolution',768))); bpy.context.scene.frame_set(1); bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(out/f'{slug}_processed.blend'))
        fmts=job.get('export_formats',['glb']);
        if 'glb' in fmts: bpy.ops.export_scene.gltf(filepath=str(out/f'{slug}.glb'),export_format='GLB',export_animations=True)
        if 'fbx' in fmts: bpy.ops.export_scene.fbx(filepath=str(out/f'{slug}.fbx'),use_selection=False,add_leaf_bones=False,bake_anim=True)
        report['checks'].update({'armature_exists':'VCF_Rig' in bpy.data.objects,'preview_rendered':preview.exists(),'glb_exported':(out/f'{slug}.glb').exists() if 'glb' in fmts else None,'fbx_exported':(out/f'{slug}.fbx').exists() if 'fbx' in fmts else None}); report['status']='complete'
    except Exception as e: report['status']='failed'; report['error']=str(e); report['traceback']=traceback.format_exc(); raise
    finally: (out/f'{slug}_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2))
if __name__=='__main__': main()def import_source(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".vox":
        import_vox(path)
    elif suffix in (".glb",".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise ValueError(f"Unsupported source format: {suffix}")

