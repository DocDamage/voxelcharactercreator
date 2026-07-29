"""CLI for the two-review generated-image to tracked VOX workflow."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from vcf_core.advanced import approve_generated_asset
from vcf_core.generation import publish_generated_asset,stage_generated_image,voxelize_approved_image
from vcf_core.operator import atomic_write_json
def main()->int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    stage=sub.add_parser("stage-image");stage.add_argument("--image",required=True);stage.add_argument("--prompt",required=True);stage.add_argument("--generator",required=True);stage.add_argument("--proposal",required=True)
    approve=sub.add_parser("approve");approve.add_argument("--proposal",required=True);approve.add_argument("--reviewer",required=True);approve.add_argument("--asset-id",required=True);approve.add_argument("--author",required=True);approve.add_argument("--license",required=True);approve.add_argument("--tags",required=True)
    voxel=sub.add_parser("voxelize");voxel.add_argument("--proposal",required=True);voxel.add_argument("--output",required=True);voxel.add_argument("--result",required=True);voxel.add_argument("--alpha-threshold",type=int,default=16);voxel.add_argument("--max-depth",type=int,default=8)
    publish=sub.add_parser("publish");publish.add_argument("--proposal",required=True);publish.add_argument("--compatible-base",required=True);publish.add_argument("--placement",default="0,0,0")
    args=parser.parse_args();proposal_path=Path(getattr(args,"proposal",""))
    if args.command=="stage-image":value=stage_generated_image(Path(args.image),prompt=args.prompt,generator=args.generator,root=ROOT);atomic_write_json(proposal_path,value)
    elif args.command=="approve":value=approve_generated_asset(json.loads(proposal_path.read_text()),reviewer=args.reviewer,asset_id=args.asset_id,author=args.author,license_id=args.license,semantic_tags=[item.strip() for item in args.tags.split(",") if item.strip()]);atomic_write_json(proposal_path,value)
    elif args.command=="voxelize":value=voxelize_approved_image(json.loads(proposal_path.read_text()),Path(args.output),root=ROOT,alpha_threshold=args.alpha_threshold,max_depth=args.max_depth);atomic_write_json(Path(args.result),value)
    else:value=publish_generated_asset(json.loads(proposal_path.read_text()),root=ROOT,compatible_base=args.compatible_base,placement=[float(item) for item in args.placement.split(",")]);print(value.relative_to(ROOT))
    return 0
if __name__=="__main__":raise SystemExit(main())
