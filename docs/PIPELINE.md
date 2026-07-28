# Pipeline

The LLM acts as the planner. It edits a validated character job. Tested Python scripts perform Blender operations deterministically.

1. Load job.
2. Import source or generate proxy.
3. Build rig.
4. Attach rigid body parts and weapon.
5. Apply animation profile.
6. Configure camera and lighting.
7. Render preview.
8. Export GLB and FBX.
9. Save processed Blend file.
10. Write validation report.

The intended user workflow is select, build, review, approve. Blender never needs to be opened manually.
