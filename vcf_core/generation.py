"""Deterministic, review-gated generated-image to VOX asset workflow."""
from __future__ import annotations
import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path
from typing import Any
from vcf_core.advanced import AdvancedValidationError, create_generation_proposal
from vcf_core.operator import atomic_write_json

PNG_SIGNATURE=b"\x89PNG\r\n\x1a\n"

def decode_png(path:Path)->tuple[int,int,list[tuple[int,int,int,int]]]:
    data=path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):raise AdvancedValidationError(["image-to-voxel input must be a PNG file"])
    offset=8; width=height=0; color_type=-1; compressed=bytearray()
    while offset<len(data):
        if offset+12>len(data):raise AdvancedValidationError(["PNG chunk is truncated"])
        length=struct.unpack_from(">I",data,offset)[0]; kind=data[offset+4:offset+8]; payload=data[offset+8:offset+8+length]; offset+=12+length
        if kind==b"IHDR":
            width,height,depth,color_type,compression,filtering,interlace=struct.unpack(">IIBBBBB",payload)
            if depth!=8 or color_type not in {2,6} or compression or filtering or interlace:raise AdvancedValidationError(["PNG must be non-interlaced 8-bit RGB or RGBA"])
        elif kind==b"IDAT":compressed.extend(payload)
        elif kind==b"IEND":break
    if not 1<=width<=126 or not 1<=height<=126:raise AdvancedValidationError(["PNG dimensions must be from 1 to 126 pixels"])
    channels=4 if color_type==6 else 3; stride=width*channels
    try:raw=zlib.decompress(bytes(compressed))
    except zlib.error as exc:raise AdvancedValidationError([f"PNG image data is invalid: {exc}"]) from exc
    if len(raw)!=(stride+1)*height:raise AdvancedValidationError(["PNG scanline length is invalid"])
    rows=[]; previous=bytearray(stride); cursor=0
    for _y in range(height):
        filter_type=raw[cursor]; cursor+=1; encoded=raw[cursor:cursor+stride];cursor+=stride; row=bytearray(stride)
        for index,value in enumerate(encoded):
            left=row[index-channels] if index>=channels else 0; up=previous[index]; upper_left=previous[index-channels] if index>=channels else 0
            if filter_type==0:predictor=0
            elif filter_type==1:predictor=left
            elif filter_type==2:predictor=up
            elif filter_type==3:predictor=(left+up)//2
            elif filter_type==4:
                estimate=left+up-upper_left; distances=(abs(estimate-left),abs(estimate-up),abs(estimate-upper_left)); predictor=(left,up,upper_left)[distances.index(min(distances))]
            else:raise AdvancedValidationError([f"PNG uses unsupported filter {filter_type}"])
            row[index]=(value+predictor)&255
        rows.append(row);previous=row
    pixels=[]
    for row in rows:
        for x in range(width):
            values=row[x*channels:(x+1)*channels];pixels.append((values[0],values[1],values[2],values[3] if channels==4 else 255))
    return width,height,pixels

def _chunk(kind:bytes,payload:bytes)->bytes:return kind+struct.pack("<II",len(payload),0)+payload
def _dictionary(values:dict[str,str])->bytes:
    result=[struct.pack("<i",len(values))]
    for key,value in values.items():
        for item in (key,value):raw=item.encode();result.append(struct.pack("<i",len(raw))+raw)
    return b"".join(result)

def image_to_vox_bytes(path:Path,*,alpha_threshold:int=16,max_depth:int=8,semantic_name:str="generated_part")->bytes:
    if not 0<=alpha_threshold<=255 or not 1<=max_depth<=126:raise AdvancedValidationError(["alpha_threshold must be 0..255 and max_depth 1..126"])
    width,height,pixels=decode_png(path); palette=[]; palette_index={}; voxels=[]
    for row in range(height):
        for x in range(width):
            red,green,blue,alpha=pixels[row*width+x]
            if alpha<alpha_threshold:continue
            color=(red,green,blue)
            if color not in palette_index:
                if len(palette)>=255:
                    color=min(palette,key=lambda item:sum((item[i]-color[i])**2 for i in range(3)))
                else:palette.append(color);palette_index[color]=len(palette)
            depth=max(1,round(((red+green+blue)/765)*max_depth))
            for z in range(depth):voxels.append((x,height-1-row,z,palette_index[color]+1))
    if not voxels:raise AdvancedValidationError(["image contains no visible pixels above alpha_threshold"])
    xyzi=struct.pack("<I",len(voxels))+b"".join(bytes(voxel) for voxel in voxels); rgba=bytearray(1024)
    for index,color in enumerate(palette):rgba[index*4:index*4+4]=bytes((*color,255))
    shape=struct.pack("<i",1)+_dictionary({"_name":semantic_name})+struct.pack("<i",1)+struct.pack("<i",0)+_dictionary({})
    transform=struct.pack("<i",0)+_dictionary({"_name":semantic_name})+struct.pack("<iiii",1,-1,-1,1)+_dictionary({"_t":"0 0 0"})
    children=b"".join((_chunk(b"SIZE",struct.pack("<III",width,height,max_depth)),_chunk(b"XYZI",xyzi),_chunk(b"RGBA",bytes(rgba)),_chunk(b"nTRN",transform),_chunk(b"nSHP",shape)))
    return b"VOX "+struct.pack("<I",150)+b"MAIN"+struct.pack("<II",0,len(children))+children

def stage_generated_image(path:Path,*,prompt:str,generator:str,root:Path)->dict[str,Any]:
    decode_png(path)
    return create_generation_proposal(prompt=prompt,generator=generator,outputs=[path],root=root)

def voxelize_approved_image(image_proposal:dict[str,Any],output:Path,*,root:Path,alpha_threshold:int=16,max_depth:int=8)->dict[str,Any]:
    if image_proposal.get("status")!="approved":raise AdvancedValidationError(["image-to-voxel requires an approved generated-image proposal"])
    outputs=image_proposal.get("outputs",[])
    if len(outputs)!=1:raise AdvancedValidationError(["approved image proposal must contain exactly one output"])
    image=(root/outputs[0]["path"]).resolve(); generated=(root/"assets"/"generated").resolve()
    if not output.resolve().is_relative_to(generated) or output.suffix.lower()!=".vox":raise AdvancedValidationError(["voxel output must be a .vox file under assets/generated"])
    semantic=image_proposal.get("approval",{}).get("semantic_tags",["generated_part"])[0]
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(image_to_vox_bytes(image,alpha_threshold=alpha_threshold,max_depth=max_depth,semantic_name=semantic))
    proposal=create_generation_proposal(prompt=f"image-to-voxel:{outputs[0]['sha256']}",generator="vcf.image_to_voxel.v1",outputs=[output],root=root)
    proposal["derived_from_sha256"]=outputs[0]["sha256"];proposal["settings"]={"alpha_threshold":alpha_threshold,"max_depth":max_depth}
    return proposal

def publish_generated_asset(proposal:dict[str,Any],*,root:Path,compatible_base:str,placement:list[float])->Path:
    approval=proposal.get("approval")
    if proposal.get("status")!="approved" or not isinstance(approval,dict):raise AdvancedValidationError(["asset publication requires an approved voxel proposal"])
    outputs=proposal.get("outputs",[])
    if len(outputs)!=1 or Path(outputs[0].get("path","")).suffix.lower()!=".vox":raise AdvancedValidationError(["approved asset proposal must contain exactly one VOX output"])
    if not isinstance(placement,list) or len(placement)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in placement):raise AdvancedValidationError(["asset placement must be a three-number vector"])
    asset_id=approval["asset_id"];source=root/outputs[0]["path"]
    target=root/"assets"/"original"/"generated"/f"{asset_id}.vox";thumbnail=target.parent/"thumbnails"/f"{asset_id}.svg";target.parent.mkdir(parents=True,exist_ok=True);thumbnail.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    thumbnail.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="160" fill="#18202b"/><text x="80" y="84" fill="white" text-anchor="middle">{asset_id}</text></svg>',encoding="utf-8")
    manifest={"schema_version":1,"asset_id":asset_id,"version":"1.0.0","kind":"body_part","source_path":target.relative_to(root).as_posix(),"format":"vox","semantic_tags":approval["semantic_tags"],"compatible_bases":[compatible_base],"pivots":{"origin":[0,0,0]},"palette_roles":["generated"],"author":approval["author"],"license":approval["license"].upper(),"provenance":f"Reviewed generated asset; generator={proposal['generator']}; prompt_sha256={proposal['prompt_sha256']}; reviewer={approval['reviewer']}","source_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"thumbnail_path":thumbnail.relative_to(root).as_posix(),"placement_voxels":placement,"scale_metadata":{"voxel_unit_meters":.08,"coordinate_system":"right_handed_z_up"}}
    manifest_path=root/"assets"/"manifests"/f"generated_{asset_id}.assets.v1.json";atomic_write_json(manifest_path,{"catalog_schema_version":1,"assets":[manifest]});return manifest_path
