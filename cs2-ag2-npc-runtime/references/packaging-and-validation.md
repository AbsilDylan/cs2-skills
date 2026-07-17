# Packaging And Clean-Client Validation

## Contents

- [Build A Resource Closure](#build-a-resource-closure)
- [Choose Stable Addon Roots](#choose-stable-addon-roots)
- [Treat Relocation As A Rebuild](#treat-relocation-as-a-rebuild)
- [Validate The Workshop Artifact](#validate-the-workshop-artifact)
- [Use The Failure Matrix](#use-the-failure-matrix)
- [Publish A Reproducible Handoff](#publish-a-reproducible-handoff)

## Build A Resource Closure

Start from the model and recursively collect every reachable resource. Include:

```text
VMDL model
primary and secondary skeletons
VNMGraph root and referenced/external graphs
all reachable VNMClips
materials and every texture they reference
particle definitions and child particles/materials/models
soundevent manifests and sound resources
physics/collision resources when required
```

Do not infer closure from filenames or one gameplay recording. Read compiled resource references and the decompiled graph.

Keep a manifest with:

```text
logical resource path
source provenance
source hash
compiled output path
parent resource(s)
license/redistribution status
validation status
```

Never put extracted proprietary compiled assets in a public skill repository. The manifest and derived parameter contract can be public when they contain no protected asset data.

## Choose Stable Addon Roots

Prefer conventional namespaced roots:

```text
models/<addon>/...
materials/<addon>/...
animation/<addon>/...
particles/<addon>/...
soundevents/<addon>/...
sounds/<addon>/...
```

Preserve the resource paths referenced by the model and graph. When graphs, skeletons, or clips live under `animation/...`, first inspect whether the addon's existing search/package roots already include that directory. Editing `gameinfo.gi` or equivalent configuration requires explicit user approval: create a timestamped backup, record the pre-edit hash, present the exact diff, validate in staging, and prove restoration before deployment. Confirm the final resources are present in the downloaded VPK.

## Treat Relocation As A Rebuild

A compiled Source 2 resource contains references beyond its filesystem filename. Copying `graph.vnmgraph_c` to another directory can leave internal references pointing to the old graph, skeleton, or clips.

Preferred order:

1. Change source paths in editable VMDL/VNMGraph/VNMClip/KV3/DMX inputs.
2. Recompile in dependency order.
3. Inspect the compiled resource reference blocks.
4. Validate the model at the final logical path.

If source is unavailable and binary rewriting is legally and technically appropriate, inspect all affected blocks, including external reference/resource tables and string-bearing data. Recompute resource identifiers using tooling proven for the current build. Do not patch only visible strings.

Archived builds have used normalized logical-path hashes for some `ResourceId_t` values, but that does not establish a universal algorithm or seed. Recover and validate the exact target build before any binary rewrite. Prefer the target build's ResourceCompiler/toolchain to manual hashing.

After any relocation, compare:

```text
model -> graph identifier/reference
graph -> skeleton
graph -> clip resources
graph -> referenced/external graphs
model/material/particle dependencies
runtime CModel AG2 entry
controller primary/definition/instance
```

## Validate The Workshop Artifact

Test four distinct trees, keeping authoring and staging isolated from a live production server:

1. **Authoring content:** editable sources.
2. **Local compiled addon:** output under `game/csgo_addons/<addon>`.
3. **Uploaded Workshop artifact:** publisher input/VPK.
4. **Downloaded client artifact:** what a new subscriber receives.

The fourth is authoritative for community delivery. Perform native/controller probes on a non-player staging instance with a watchdog and remote restart path before production rollout.

For each release:

- record Workshop file ID, upload/update timestamp, and artifact size;
- force or verify a fresh download without loose copies masking failures;
- list VPK entries and check every manifest path;
- compare hashes of critical compiled resources where possible;
- connect with no custom files in the base `game/csgo` tree;
- capture client and server resource/animation errors;
- prove the runtime materialization ladder remotely.

Do not copy files into a tester's base client tree during a clean-client test. Loose client resources can make a broken Workshop appear valid.

Precache resource manifests, not arbitrary event names. For sounds, precache the `.vsndevts` resource and emit the event name defined inside it. Apply the same closure discipline to particle children and material shaders.

## Use The Failure Matrix

| Evidence | Most likely layer | Next action |
|---|---|---|
| File absent from downloaded VPK | publisher root/filter/closure | fix AddonConfig or stage manifest |
| File present but ResourceStatus missing/error | path normalization or corrupt compile | inspect logical path and recompile |
| Model and graph Resident, CModel table empty | model runtime metadata/construction | compare model compile and provenance |
| CModel key absent | graph identifier mismatch | compare controller key and model entries |
| Key match, value zero | unresolved resource ID/reference | rebuild references and IDs |
| Primary nonzero, definition zero | graph/skeleton/clip resolution | inspect graph closure and compiler errors |
| Definition nonzero, instance zero | runtime compatibility/instance creation | inspect skeleton/variation and server logs |
| Instance valid, parameters missing | wrong graph, wrong names, or type bridge | compare decompiled control contract |
| Local client works, clean client fails | loose-file contamination or Workshop omission | remove masking files and inspect VPK |

## Publish A Reproducible Handoff

Include:

- source and compiled logical paths;
- exact compiler/viewer versions and commands;
- addon root configuration assumptions;
- resource closure manifest;
- Workshop ID and downloaded-artifact verification;
- current CS2 client/server builds;
- clean-client test steps and observed results;
- any binary rewrite/hash algorithm evidence;
- known unsupported graph branches or missing assets;
- ownership and redistribution constraints.

Separate generated outputs from hand-authored inputs. Keep local extracted references under an ignored `.local/` or equivalent directory so a public commit cannot accidentally include them.
