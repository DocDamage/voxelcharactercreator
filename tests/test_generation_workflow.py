from __future__ import annotations
import json,struct,tempfile,unittest,zlib
from pathlib import Path
from blender_worker.adapters.vox_reader import read_vox
from vcf_core.advanced import AdvancedValidationError,approve_generated_asset
from vcf_core.assets.registry import validate_manifest
from vcf_core.generation import decode_png,publish_generated_asset,stage_generated_image,voxelize_approved_image

def png(width:int,height:int,pixels:list[tuple[int,int,int,int]])->bytes:
    def chunk(kind,payload):return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff)
    raw=b"".join(b"\0"+b"".join(bytes(pixel) for pixel in pixels[y*width:(y+1)*width]) for y in range(height))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,6,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b"")

class GenerationWorkflowTests(unittest.TestCase):
    def test_two_reviews_produce_a_valid_provenance_tracked_vox_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); image=root/"assets"/"generated"/"concept.png";image.parent.mkdir(parents=True);image.write_bytes(png(2,2,[(255,0,0,255),(0,255,0,255),(0,0,255,255),(0,0,0,0)]))
            self.assertEqual((2,2),decode_png(image)[:2]); staged=stage_generated_image(image,prompt="original body",generator="fixture",root=root)
            with self.assertRaises(AdvancedValidationError):voxelize_approved_image(staged,root/"assets"/"generated"/"part.vox",root=root)
            image_approved=approve_generated_asset(staged,reviewer="reviewer",asset_id="concept_image",author="Artist",license_id="cc0-1.0",semantic_tags=["body"])
            vox_proposal=voxelize_approved_image(image_approved,root/"assets"/"generated"/"part.vox",root=root,max_depth=4);self.assertEqual("review_required",vox_proposal["status"])
            document=read_vox(root/"assets"/"generated"/"part.vox");self.assertEqual(3,len(document.models[0].voxels))
            asset_approved=approve_generated_asset(vox_proposal,reviewer="reviewer",asset_id="generated_body",author="Artist",license_id="cc0-1.0",semantic_tags=["body"])
            manifest_path=publish_generated_asset(asset_approved,root=root,compatible_base="quadruped_standard",placement=[0,0,0]);payload=json.loads(manifest_path.read_text())["assets"][0]
            self.assertEqual([],validate_manifest(payload,root));self.assertIn("prompt_sha256",payload["provenance"])

if __name__=="__main__":unittest.main()
