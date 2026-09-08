---
name: cs2-animgraph2-authoring
description: "Author, compile, debug, and package original CS2 AnimGraph2 graphs and clips for server-owned NPCs, weapons, and items, including CNmGraphDocument, private roots, routing, and Workshop delivery."
---

# CS2 AnimGraph2 Authoring

Build reproducible AnimGraph2 resources for server-owned NPCs and weapon/item
presentation against the current installed CS2 toolchain. Treat source-document
and clip authoring, graph selection,
entity/controller ownership, client identity, player graph ownership, Workshop
delivery, prediction, and server gameplay as separate contracts. Compilation is
evidence of syntax acceptance, not runtime success.

This skill owns original text `CNmGraphDocument` sources, weapon/item and
server-owned NPC VNMClip/VNMGraph resources, private first- and third-person
graph roots, owner/world item models, client-visible proxy routing,
prediction-aware server integration, and resource closure. It does not own:

- player mesh, rig, skin weights, first-person body geometry, hitboxes, or
  ragdolls; use `$cs2-player-model-porting`;
- `CBaseAnimGraphController` materialization or server-driven model-entity NPC
  parameters; use `$cs2-ag2-npc-runtime`;
- NPC behavior, navigation, combat, spawning, or lifecycle orchestration; use
  `$cs2-server-npc-runtime` when that skill is available.

## Select The Relevant Reference

- Read [source-graph-authoring.md](references/source-graph-authoring.md) for
  original `CNmGraphDocument` generation, deterministic graph IR, current-build
  compiler profiling, the minimal original L0 fixture, typed controls, and
  validation gates.
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
- Read [weapon-presentation-contracts.md](references/weapon-presentation-contracts.md)
  for visible-but-misaligned weapons, agent appearance overrides, secondary-root
  transforms, hand fitting, charge/rotation, muzzle positions and sound ownership.

Load only the references needed for the current failure. For an end-to-end new
item, follow the tooling, authoring, routing and delivery references as needed;
load the presentation reference when integrating those surfaces. For a
server-owned NPC, begin with `source-graph-authoring.md`, then route runtime ownership to
`$cs2-ag2-npc-runtime` and behavior to `$cs2-server-npc-runtime`.

## Non-Negotiable Rules

1. Use the current installed game and tools as the authority. Record revision,
   paths, tool hashes, source hashes, commands, warnings, and evidence level.
2. Preserve untouched inputs. Keep locally extracted Valve material outside
   version control and public artifacts.
3. Generate graphs, clips and models only under declared private namespaces.
   Never shadow Valve graph/model paths or write loose test files to base
   `game/csgo`. An intentional canonical VData integration is a separate,
   authorized operation described in the presentation reference; the bundled
   private-resource stager does not permit global-path outputs.
4. Keep first- and third-person skeletons, clips, graph instances, object
   models, and validation views distinct.
5. For a weapon/item, route the `weapon_type` and variation the client actually
   resolves. A server-only VData pointer or entity marker does not register
   client identity.
6. For player-owned graphs, preserve required attachments and final hand-IK
   topology unless a measured current-build replacement is proven.
7. Prefer editable source compilation. Limit binary graph work to offline,
   hash-gated private copies; never patch a DLL, process memory, anti-cheat, or
   network trust boundary.
8. Refuse destructive staging or configuration edits by default. Installed
   CS2/Workshop configuration changes require explicit approval, preimage hash,
   backup, exact diff, and restoration plan.
9. Establish compiled-resource and downloaded-VPK evidence for initial
   integration and relevant delivery debugging. For routine publication under
   an agreed deployment fast path, reuse existing asset evidence and perform
   transport/revision and runtime health checks without repeating a full asset
   audit. Neither a local file nor a transfer proves client rendering.
10. Keep gameplay server-authoritative. For predicted items, do not continuously
    fight native prediction; for NPCs, project behavior state into presentation.
    Model actions with explicit cancel, completion, restoration, and
    stale-callback protection.
11. Export clip DMX in the compiler frame (Source 2 Viewer >= 19.2
    convention). A clip written in the raw axes of an older decompile compiles
    cleanly and renders nothing; the bundled exporter converts root-level
    bones by default.
12. Treat every Nm compiler registration and node schema as build-profiled.
    Never modify the installed Valve asset registry implicitly, redistribute a
    Valve tool or registry, or promote a compiled graph across compiler
    fingerprints.

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

For a client-predicted weapon or item:

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

For a server-owned NPC:

```text
server plugin
  model set before spawn + use_animgraph + AnimateOnServer

CModel graph table
  -> controller -> definition -> instance
  -> typed controls -> graph resources and clips

Workshop VPK
  private model, graph, skeleton, clip, material, and texture closure
```

This skill authors the resources. Route controller materialization and typed
parameter writes to `$cs2-ag2-npc-runtime`, and AI/navigation/combat to
`$cs2-server-npc-runtime`. A pure server-owned NPC has no proxy, `weapon_type`,
HUD-model, or first-person validation requirement.

## Weapon And Item End-To-End Workflow

For a greenfield server-owned NPC graph, follow
`source-graph-authoring.md`'s promotion ladder instead of applying the
predicted-proxy steps below.

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

On the measured player-owned weapon path, moving parts use the character
clip's secondary weapon animation. Declare the matching skeleton and its joints.
Keep the Blender parent, DMX export parent and runtime attachment distinct:
`wpn` as a runtime attachment does not require DMX parenting under `wpn`.
Compare compiled secondary-root transforms with the stock control as described
in [weapon-presentation-contracts.md](references/weapon-presentation-contracts.md).
Preserve measured wrist, finger and elbow constraints when fitting the grip.

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
to manufacture rights. Establish staged and downloaded VPK closure for the
initial integration or a relevant delivery failure. For routine deployment,
use the agreed verification scope described in
[workshop-runtime-and-debugging.md](references/workshop-runtime-and-debugging.md).

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

Declare the authored integration complete only when:

- the build reproduces from untouched authorized project sources;
- generated graph/clip/model paths are private, and any canonical VData
  override has an explicit scope and separately controlled integration;
- stock/decompiled compiler dependencies are absent from the public artifact;
- template and transitive-input provenance permits every artifact byte to be
  redistributed, with the exact basis recorded;
- source/reference/tool/compiled/VPK hashes are recorded and mutually linked;
- every applicable graph identity, variation, control, and action route is
  observed;
- a weapon/item passes both first- and third-person clean-client validation;
- a pure server-owned NPC passes local and remote-observer clean-client
  validation; first-person proxy requirements are not applicable;
- the server lifecycle does not leak native gameplay or restart/cancel visuals;
- applicable stock/proxy and unrelated actors pass negative controls, or the
  enforced exclusivity boundary is documented;
- limitations and pending validation layers are explicit.

If only source generation or compilation passed, report that exact state. Do
not call the result packaged, route-proven, runtime-valid, or distributable.
