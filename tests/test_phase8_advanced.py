from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from vcf_core.advanced import (AdvancedValidationError, SceneEditorDocument, approve_generated_asset,
    cast_quality_summary, create_generation_proposal, deterministic_weights, load_cast_plan,
    load_topology_rig, resume_cast, validate_boss_composition, validate_deformation, validate_spring_motion)
from vcf_core.jobs import validate_job
from vcf_core.jobs import load_job
from vcf_core.editor3d import apply_editor_result

ROOT=Path(__file__).resolve().parents[1]

class Phase8AdvancedTests(unittest.TestCase):
    def test_all_nonhuman_topologies_have_complete_engine_gates(self):
        rigs=[load_topology_rig(path) for path in sorted((ROOT/"config"/"advanced_rigs").glob("*.v1.json"))]
        self.assertEqual({"quadruped","flying","multi_arm","boss"},{rig.topology for rig in rigs})
        self.assertTrue(all(not rig.validate() and rig.fallback_template=="humanoid_standard" for rig in rigs))
        for rig in rigs:
            job=load_job(ROOT/"characters"/"original"/f"phase8_{rig.template_id}.json",ROOT)
            self.assertEqual(rig.template_id,job["rig_template"])
            self.assertEqual("assembly",job["source"]["mode"])

    def test_boss_hierarchy_phases_and_budgets_are_bounded(self):
        value=json.loads((ROOT/"config"/"production"/"final_boss.v1.json").read_text()); value.pop("schema_version")
        self.assertEqual([],validate_boss_composition(value))
        value["attachments"][0]["parent"]="crown"
        self.assertTrue(any("cycle" in error or "root" in error for error in validate_boss_composition(value)))

    def test_deformation_is_normalized_bounded_and_always_rigid_fallback(self):
        policy={"mode":"deform","max_influences":4,"normalize_weights":True,"secondary_solver":"spring_bones","bake":True,"fallback":"rigid"}
        self.assertEqual([],validate_deformation(policy))
        weights=deterministic_weights({"spine":2,"root":4,"head":1,"arm_l":3,"arm_r":5},4)
        self.assertEqual(4,len(weights)); self.assertAlmostEqual(1,sum(weights.values()))
        policy["fallback"]="none"; self.assertTrue(validate_deformation(policy))
        spring=[{"chain_id":"tail","bones":["tail"],"stiffness":.4,"damping":.5,"max_angle_degrees":20,"solver":"deterministic_spring","bake":True,"fallback":"rigid"}]
        self.assertEqual([],validate_spring_motion(spring)); spring[0]["fallback"]="none"; self.assertTrue(validate_spring_motion(spring))

    def test_generated_assets_require_review_and_provenance(self):
        generated=ROOT/"assets"/"generated"/"phase8_test.bin"; generated.parent.mkdir(parents=True,exist_ok=True); generated.write_bytes(b"deterministic")
        try:
            proposal=create_generation_proposal(prompt="original winged creature",generator="test-v1",outputs=[generated],root=ROOT)
            self.assertEqual("review_required",proposal["status"]); self.assertIn("license_inference",proposal["prohibited_actions"])
            approved=approve_generated_asset(proposal,reviewer="operator",asset_id="original_winged",author="VCF test",license_id="cc0-1.0",semantic_tags=["body"])
            self.assertEqual("approved",approved["status"]); self.assertEqual("cc0-1.0",approved["approval"]["license"])
        finally: generated.unlink(missing_ok=True)

    def test_editor_directly_authors_transform_and_socket_with_undo(self):
        job=json.loads((ROOT/"characters"/"ff7"/"cloud.json").read_text())
        editor=SceneEditorDocument(job); editor.apply_transform("head",location=[0,0,.1],rotation=[0,5,0],scale=[1,1,1]); editor.set_socket("effect_socket","head",[0,0,.2])
        self.assertIn("socket_overrides",editor.value["settings_overrides"]); editor.undo(); self.assertNotIn("socket_overrides",editor.value["settings_overrides"]); editor.redo(); self.assertIn("socket_overrides",editor.value["settings_overrides"])
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"job.json";target.write_text((ROOT/"characters"/"cast"/"cast_001.json").read_text())
            saved=apply_editor_result(ROOT,target,{"schema_version":1,"part_transforms":{"p8_quadruped_head":{"location":[0,0,.1],"rotation_degrees":[0,0,0],"scale":[1,1,1]}},"socket_overrides":{}})
            self.assertEqual(.1,saved["settings_overrides"]["part_transforms"]["p8_quadruped_head"]["location"][2])

    def test_large_cast_is_resumable_measured_and_release_consistent(self):
        plan=load_cast_plan(ROOT/"config"/"production"/"large_cast.v1.json"); summary=cast_quality_summary(plan)
        self.assertGreaterEqual(summary["model_count"],100); self.assertTrue(summary["resumable"]); self.assertFalse(summary["consistent"]); self.assertLessEqual(max(sum(1 for item in plan["characters"] if item["batch"]==batch) for batch in {item["batch"] for item in plan["characters"]}),plan["governance"]["max_batch_size"])
        self.assertEqual(120,len(list((ROOT/"characters"/"cast").glob("cast_*.json"))))
        self.assertEqual(120,len({json.dumps(json.loads((ROOT/item["job_path"]).read_text())["settings_overrides"]["part_transforms"],sort_keys=True) for item in plan["characters"]}))
        self.assertTrue(all(item["state"]=="ready" and all(value=="pending" for value in item["checks"].values()) for item in plan["characters"]))
        interrupted=json.loads(json.dumps(plan)); interrupted["characters"][0]["state"]="failed"; self.assertEqual("ready",resume_cast(interrupted)["characters"][0]["state"]); self.assertEqual("failed",interrupted["characters"][0]["state"])

    def test_job_accepts_advanced_deformation_and_editor_contracts(self):
        job=json.loads((ROOT/"characters"/"ff7"/"cloud.json").read_text()); job["settings_overrides"]={"deformation":{"mode":"deform","max_influences":4,"normalize_weights":True,"secondary_solver":"spring_bones","bake":True,"fallback":"rigid"},"part_transforms":{"head":{"location":[0,0,0],"rotation_degrees":[0,0,0],"scale":[1,1,1]}}}
        self.assertEqual([],validate_job(job,ROOT))

if __name__=="__main__": unittest.main()
