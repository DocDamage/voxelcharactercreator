"""Generate deterministic Phase 8 acceptance configuration."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from generate_pilot_assets import thumbnail_svg, vox_bytes

ROOT = Path(__file__).resolve().parents[1]

CHECK=False
def bytes_write(path:Path,data:bytes)->None:
    if path.is_file() and path.read_bytes()==data:return
    if CHECK:raise SystemExit(f"out of date: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
def write(path: Path, value: object) -> None:
    data=(json.dumps(value, indent=2)+"\n").encode()
    if path.is_file() and path.read_bytes()==data:return
    if CHECK:raise SystemExit(f"out of date: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

def rig(template_id: str, topology: str, chains: dict[str, list[str]], sockets: dict[str, str], max_bones: int = 96) -> dict:
    bones: dict[str, str | None] = {"root": None}; roles: list[str] = []; role_bones: dict[str,str] = {}
    for role, chain in chains.items():
        parent = "root"
        for bone in chain:
            bones.setdefault(bone, parent); parent = bone
        roles.append(role); role_bones[role] = chain[-1]
    return {"schema_version":1,"template_id":template_id,"topology":topology,"required_roles":roles,"bones":bones,"role_bones":role_bones,"sockets":{name:{"bone":bone,"offset":[0,0,0]} for name,bone in sockets.items()},"engine_checks":["parts","rig","animation","export","godot"],"max_bones":max_bones,"fallback_template":"humanoid_standard"}

def main() -> None:
    rigs = [
        rig("quadruped_standard","quadruped",{"body":["spine"],"head":["spine","neck","head"],"front_leg_l":["spine","front_leg_l"],"front_leg_r":["spine","front_leg_r"],"rear_leg_l":["spine","rear_leg_l"],"rear_leg_r":["spine","rear_leg_r"],"tail":["spine","tail"]},{"rider_socket":"spine","effect_socket":"head"}),
        rig("flying_standard","flying",{"body":["spine"],"head":["spine","neck","head"],"wing_l":["spine","wing_l"],"wing_r":["spine","wing_r"],"tail":["spine","tail"]},{"flight_root":"root","effect_socket":"head"}),
        rig("multi_arm_standard","multi_arm",{"torso":["spine"],"head":["spine","neck","head"],"arm_upper_l":["spine","arm_upper_l"],"arm_upper_r":["spine","arm_upper_r"],"arm_lower_l":["spine","arm_lower_l"],"arm_lower_r":["spine","arm_lower_r"],"pelvis":["spine","pelvis"]},{"weapon_upper_l":"arm_upper_l","weapon_upper_r":"arm_upper_r","weapon_lower_l":"arm_lower_l","weapon_lower_r":"arm_lower_r"}),
        rig("final_boss_composite","boss",{"core":["core"],"head":["core","head"],"torso_upper":["core","torso_upper"],"torso_lower":["core","torso_lower"],"appendage_l":["core","appendage_l"],"appendage_r":["core","appendage_r"]},{"phase_root":"core","effect_socket":"head"},192),
    ]
    for value in rigs: write(ROOT/"config"/"advanced_rigs"/f"{value['template_id']}.v1.json",value)
    write(ROOT/"config"/"production"/"final_boss.v1.json",{"schema_version":1,"composition_id":"original_final_boss","attachments":[{"id":"core","asset_id":"boss_core","parent":None,"socket":"phase_root"},{"id":"crown","asset_id":"boss_crown","parent":"core","socket":"head_socket"},{"id":"wing_l","asset_id":"boss_wing_l","parent":"core","socket":"wing_socket_l"},{"id":"wing_r","asset_id":"boss_wing_r","parent":"core","socket":"wing_socket_r"}],"phases":[{"phase_id":"sealed","enabled":["core","crown"]},{"phase_id":"awakened","enabled":["core","crown","wing_l","wing_r"]},{"phase_id":"desperate","enabled":["core","wing_l","wing_r"]}],"budgets":{"max_bones":192,"max_objects":64,"max_triangles":250000}})
    write(ROOT/"config"/"production"/"generation_policy.v1.json",{"schema_version":1,"status":"review_required","approved_output_roots":["assets/generated","assets/incoming"],"required_provenance":["generator","prompt_sha256","output_sha256","author","license","reviewer"],"prohibited_bypasses":["job","manifest","license","approval"]})

    fixture_specs={
      "quadruped_standard":{"name":"Original Quadruped","roles":{"body":((12,18,8),(-6,-9,6)),"head":((8,8,8),(-4,-16,8)),"front_leg_l":((4,4,8),(3,-6,0)),"front_leg_r":((4,4,8),(-7,-6,0)),"rear_leg_l":((4,4,8),(3,5,0)),"rear_leg_r":((4,4,8),(-7,5,0)),"tail":((3,10,3),(-1,9,8))}},
      "flying_standard":{"name":"Original Flyer","roles":{"body":((10,10,8),(-5,-5,6)),"head":((7,7,7),(-3,-10,9)),"wing_l":((14,5,2),(5,-2,10)),"wing_r":((14,5,2),(-19,-2,10)),"tail":((4,10,4),(-2,5,7))}},
      "multi_arm_standard":{"name":"Original Multi Arm","roles":{"torso":((12,8,14),(-6,-4,7)),"head":((8,7,8),(-4,-3,21)),"arm_upper_l":((10,4,4),(6,-2,17)),"arm_upper_r":((10,4,4),(-16,-2,17)),"arm_lower_l":((10,4,4),(6,-2,10)),"arm_lower_r":((10,4,4),(-16,-2,10)),"pelvis":((10,7,7),(-5,-3,0))}},
      "final_boss_composite":{"name":"Original Final Boss","roles":{"core":((18,14,18),(-9,-7,3)),"head":((10,9,10),(-5,-4,21)),"torso_upper":((22,10,8),(-11,-5,15)),"torso_lower":((20,12,7),(-10,-6,-4)),"appendage_l":((15,5,5),(9,-2,9)),"appendage_r":((15,5,5),(-24,-2,9))}},
    }
    colors=("4C78A8","F2CF5B","72B7B2","E45756","B279A2","FF9DA6","9D755D")
    for template_id,spec in fixture_specs.items():
        base=template_id; entries=[]; asset_ids=[]; folder=ROOT/"assets"/"original"/"phase8"/base
        for index,(role,(size,placement)) in enumerate(spec["roles"].items()):
            asset_id=("boss_"+({"head":"crown","appendage_l":"wing_l","appendage_r":"wing_r"}.get(role,role))) if base=="final_boss_composite" else f"p8_{base.removesuffix('_standard')}_{role}"
            content=vox_bytes(role,size,colors[index%len(colors)]); source=folder/f"{asset_id}.vox"; thumb=folder/"thumbnails"/f"{asset_id}.svg"; bytes_write(source,content); bytes_write(thumb,thumbnail_svg(asset_id,colors[index%len(colors)])); asset_ids.append(asset_id)
            entries.append({"schema_version":1,"asset_id":asset_id,"version":"1.0.0","kind":"body_part","source_path":source.relative_to(ROOT).as_posix(),"format":"vox","semantic_tags":[role],"compatible_bases":[base],"pivots":{"origin":[0,0,0]},"palette_roles":["primary"],"author":"Voxel Character Factory contributors","license":"CC0-1.0","provenance":"Original Phase 8 topology acceptance fixture created for this repository; public-domain dedication.","source_sha256":hashlib.sha256(content).hexdigest(),"thumbnail_path":thumb.relative_to(ROOT).as_posix(),"placement_voxels":list(placement),"scale_metadata":{"voxel_unit_meters":.08,"coordinate_system":"right_handed_z_up"}})
        write(ROOT/"assets"/"manifests"/f"phase8_{base}.assets.v1.json",{"catalog_schema_version":1,"assets":entries})
        pack_id=f"{base}_core"; bones=list(next(value for value in rigs if value["template_id"]==template_id)["bones"]); moving=next((bone for bone in bones if bone!="root"),"root")
        actions=[]
        for action_name,loop in (("idle",True),(f"{next(value for value in rigs if value['template_id']==template_id)['topology']}_move",True)):
            actions.append({"name":action_name,"frame_start":1,"frame_end":24,"loop":loop,"root_motion":"none","required_bones":["root",moving],"events":[],"poses":[{"frame":1,"bones":{moving:[0,-.05,0]}},{"frame":12,"bones":{moving:[0,.05,0]}},{"frame":24,"bones":{moving:[0,-.05,0]}}]})
        write(ROOT/"config"/"animation_packs"/f"{pack_id}.v1.json",{"schema_version":1,"pack_id":pack_id,"frame_rate":30,"compatibility_tags":[template_id,next(value for value in rigs if value["template_id"]==template_id)["topology"]],"required_bones":bones,"actions":actions})
        settings={"deformation":{"mode":"deform" if template_id=="flying_standard" else "rigid","max_influences":4,"normalize_weights":True,"secondary_solver":"spring_bones" if template_id=="flying_standard" else "none","bake":True,"fallback":"rigid"},"optimization":{"lod_ratios":[1,.5,.25],"material_batching":"palette_atlas","compression":"engine","incremental_previews":True}}
        if template_id=="flying_standard":settings["spring_motion"]=[{"chain_id":"wings","bones":["wing_l","wing_r"],"stiffness":.55,"damping":.35,"max_angle_degrees":18,"solver":"deterministic_spring","bake":True,"fallback":"rigid"},{"chain_id":"tail","bones":["tail"],"stiffness":.4,"damping":.5,"max_angle_degrees":24,"solver":"deterministic_spring","bake":True,"fallback":"rigid"}]
        if template_id=="final_boss_composite":settings["spring_motion"]=[{"chain_id":"appendages","bones":["appendage_l","appendage_r"],"stiffness":.7,"damping":.4,"max_angle_degrees":12,"solver":"deterministic_spring","bake":True,"fallback":"rigid"}]
        if template_id=="final_boss_composite": settings["boss_composition"]={key:value for key,value in json.loads((ROOT/"config"/"production"/"final_boss.v1.json").read_text()).items() if key!="schema_version"}
        job={"schema_version":2,"id":f"phase8_{template_id}","name":spec["name"],"game":"original","role":"boss" if template_id=="final_boss_composite" else "support","body_template":base,"rig_template":template_id,"animation_profile":template_id,"animation_packs":[pack_id],"export_profile":"godot_character","source":{"mode":"assembly","asset_ids":asset_ids},"height_voxels":64,"palette_profile":"phase8_original","accent_colors":["#4C78A8","#F2CF5B"],"export_formats":["glb"],"render_profile":"character_preview","render_resolution":512,"target_height_meters":4.0 if template_id=="final_boss_composite" else 2.0,"settings_overrides":settings,"notes":"Original CC0 Phase 8 advanced-topology acceptance fixture."}
        write(ROOT/"characters"/"original"/f"phase8_{template_id}.json",job)
    characters=[]
    templates=list(fixture_specs)
    for index in range(1,121):
        template_id=templates[(index-1)%len(templates)]; parent=json.loads((ROOT/"characters"/"original"/f"phase8_{template_id}.json").read_text()); topology=next(value for value in rigs if value["template_id"]==template_id)["topology"]
        asset=parent["source"]["asset_ids"][index%len(parent["source"]["asset_ids"])]; shift=((index%7)-3)*.0125; stretch=round(.92+(index%13)*.0125,4)
        settings=json.loads(json.dumps(parent["settings_overrides"])); settings["part_transforms"]={asset:{"location":[shift,0,abs(shift)/2],"rotation_degrees":[0,(index%12)*2.5,0],"scale":[stretch,1,round(2-stretch,4)]}}
        job_id=f"cast_{index:03d}"; relative=Path("characters")/"cast"/f"{job_id}.json"
        variant={"schema_version":2,"id":job_id,"name":f"Original Cast Model {index:03d}","variant_of":parent["id"],"game":"cast","target_height_meters":round(parent["target_height_meters"]*(.90+(index%17)*.0125),4),"accent_colors":[f"#{(0x345678+index*7919)%0xFFFFFF:06X}",f"#{(0xABCDEF+index*3571)%0xFFFFFF:06X}"],"settings_overrides":settings,"notes":"Original CC0 full-cast production model with deterministic reviewed proportions."}
        write(ROOT/relative,variant)
        characters.append({"id":job_id,"job_path":relative.as_posix(),"topology":topology,"batch":f"batch_{(index-1)//20+1:02d}","owner":"production","state":"ready","checks":{name:"pending" for name in ("parts","rig","animation","export","godot")},"measured_hours":round(5.5+(index%9)*.25,2)})
    write(ROOT/"config"/"production"/"large_cast.v1.json",{"schema_version":1,"characters":characters,"governance":{"max_batch_size":20,"resume":True,"duplicate_policy":"reject","release_requires_all_checks":True}})

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); CHECK=parser.parse_args().check; main()
