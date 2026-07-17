---
name: cs2-animgraph2-authoring
description: "Author, debug, and package CS2 weapon/item AnimGraph2: clips, private 1P/3P roots, stock-pose or missing-arms routing, proxy prediction, and Workshop delivery. Excludes NPCs and player meshes."
---

# CS2 AnimGraph2 Authoring

Build reproducible weapon/item presentation against the current installed CS2
toolchain. Treat clip authoring, graph selection, client identity, player graph
ownership, Workshop delivery, prediction, and server gameplay as separate
contracts. Compilation is evidence of syntax acceptance, not runtime success.

This skill owns weapon/item VNMClip and VNMGraph resources, private first- and
third-person graph roots, owner/world item models, client-visible proxy routing,
prediction-aware server integration, and item resource closure. It does not own:

- player mesh, rig, skin weights, first-person body geometry, hitboxes, or
  ragdolls; use `$cs2-player-model-porting`;
- `CBaseAnimGraphController` materialization or server-driven model-entity NPC
  parameters; use `$cs2-ag2-npc-runtime`;
- brand-new non-weapon NPC graph design without an existing graph contract;
  treat that as unsupported until a dedicated authoring workflow is selected.

## Select The Relevant Reference

- Read [portable-tooling.md](references/portable-tooling.md) for the bundled
  manifest, stock-reference extraction, Blender scene, DMX/VNMClip generation,
  safe staging, compilation, and receipts.
- Read [authoring-and-compilation.md](references/authoring-and-compilation.md)
  for model/clip contracts, skeleton choice, editable VNMClip documents,
  ResourceCompiler behavior, inspection, and build manifests.
- Read [graph-routing-and-patching.md](references/graph-routing-and-patching.md)
  for proxy identity, private graph families, first/third-person routing, IK,
  long actions, sentinels, and guarded compiled-resource transformations.
- Read [workshop-runtime-and-debugging.md](references/workshop-runtime-and-debugging.md)
  for packer roots, clean-client delivery, VData identity, prediction-safe
  server integration, overlays, and runtime diagnosis.

Load only the references needed for the current failure. For an end-to-end new
item, read all four in the order above.

## Non-Negotiable Rules

1. Use the current installed game and tools as the authority. Record revision,
   paths, tool hashes, source hashes, commands, warnings, and evidence level.
2. Preserve untouched inputs. Keep locally extracted Valve material outside
   version control and public artifacts.
3. Generate project resources only under declared private namespaces. Never
   shadow Valve graph/model paths or write loose test files to base `game/csgo`.
4. Keep first- and third-person skeletons, clips, graph instances, object
   models, and validation views distinct.
5. Route the `weapon_type` and variation the client actually resolves. A
   server-only VData pointer or entity marker does not register client identity.
6. Preserve required player attachments and final hand-IK topology unless a
   measured current-build replacement is proven.
7. Prefer editable source compilation. Limit binary graph work to offline,
   hash-gated private copies; never patch a DLL, process memory, anti-cheat, or
   network trust boundary.
8. Refuse destructive staging or configuration edits by default. Installed
   CS2/Workshop configuration changes require explicit approval, preimage hash,
   backup, exact diff, and restoration plan.
9. Inspect compiled resources and the downloaded Workshop VPK. A local output
   file does not prove packaging, mounting, routing, or animation playback.
10. Keep gameplay server-authoritative without continuously fighting native
    prediction. Model actions as idempotent transactions with explicit cancel,
    completion, restoration, and stale-callback protection.

Use evidence labels precisely:

```text
static-observed -> source-authored / generated -> roundtrip-valid (optional)
-> compiled -> inspected -> packaged -> downloaded-vpk-inspected -> mounted
-> route-proven
-> first-person-validated / third-person-validated / gameplay-validated
-> in-game-validated
```

Use only labels whose named evidence exists. `roundtrip-valid` is a DMX
serialization check, `inspected` means semantic compiled-resource inspection,
and `in-game-validated` requires every applicable visual and gameplay branch;
none is an alias for another stage.

Never infer a later label from an earlier one.

## Runtime Architecture

```text
server plugin
  native predicted proxy + authoritative gameplay/input lifecycle

client item identity
  mounted VData when proven, otherwise the proxy's observed weapon_type

player ModelDoc
  hudmodel -> private first-person root
  default/worldmodel -> private third-person root

private AnimGraph2 family
  root -> action/category child -> observed variation -> custom VNMClip

Workshop VPK
  exact allowlisted closure of project-owned compiled resources
```

The held object and player pose are independent. A custom owner/world VMDL does
not prove the HUD-arms or third-person player graph changed.

## End-To-End Workflow

### 1. Inventory and choose a baseline

Record the native entity class, observed client `weapon_type`, variation suffix,
owner/world conventions, character and item skeletons, graph family, action
set, and runtime prediction constraints. Select a current stock baseline with a
similar hold/action contract; do not assume another item is compatible.

### 2. Declare a private project

Create one canonical manifest with the addon, private namespaces, 1P/3P sets,
actions, source dependencies, compile order, artifact policy, package
allowlist, and expected reports.
Run preflight validation before extraction, staging, or compilation.

### 3. Author and inspect clips

Build against the exact current skeleton hierarchy/rest transforms. Export
complete finite channels, generate one VNMClip per canonical action, compile in
dependency order, and inspect the semantic result. Use the bundled tooling only
within its recorded platform/tool compatibility profile.

### 4. Build private graph roots

Recreate the required control/routing contract in a unique namespace. Route the
identity observed on the client, preserve IK, and implement both action and
locomotion/category branches when third-person hold poses must change.

### 5. Prove routes with sentinels

Assign unmistakable temporary poses to draw, idle, primary action, inspect, and
reload. Prove every branch independently, including return-to-idle and negative
controls, before judging animation quality.

### 6. Package from an allowlisted closure

Build/package from an isolated, manifest-owned tree. Exclude local stock
compiler dependencies and template-derived outputs whose redistribution status
is blocked. An artifact policy is an explicit provenance assertion, not a way
to manufacture rights. Inspect staged and downloaded VPK contents and compare
hashes before runtime testing.

### 7. Integrate the server proxy

Give/configure the native proxy, assign validated player/item models, implement
authoritative gameplay, and restore all state on switch, cancel, death,
disconnect, map change, and unload. Do not attempt to drive a client HUD graph
through a server-only model controller.

### 8. Validate owner and observer clients

Verify resource opening, mounted revision, selected graph/variation/action,
first-person arms/object, third-person player pose/held object, transitions,
prediction, cancellation, reconnect, and another observing clean client.

## Completion Contract

Declare the item complete only when:

- the build reproduces from untouched authorized project sources;
- every generated project path is inside one declared private namespace;
- stock/decompiled compiler dependencies are absent from the public artifact;
- template and transitive-input provenance permits every artifact byte to be
  redistributed, with the exact basis recorded;
- source/reference/tool/compiled/VPK hashes are recorded and mutually linked;
- the client-selected identity and every required action route are observed;
- first-person and third-person results both pass clean-client validation;
- the server lifecycle does not leak native gameplay or restart/cancel visuals;
- same-proxy stock and unrelated actors pass negative controls, or enforced
  proxy exclusivity is documented;
- limitations and pending validation layers are explicit.

If only source generation or compilation passed, report that exact state. Do
not call the result packaged, route-proven, runtime-valid, or distributable.
