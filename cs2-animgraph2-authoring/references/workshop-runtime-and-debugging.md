# Workshop, Runtime, And Debugging

Use this reference after sources compile. It covers Workshop packaging, clean
client tests, server-plugin responsibilities, prediction, and layered runtime
diagnostics.

## Contents

1. Packaging contract
2. Packer roots and gameinfo
3. VPK inspection
4. Server mounting
5. Plugin responsibilities
6. VData and client identity
7. Input and prediction
8. Player model lifecycle
9. Runtime diagnostics
10. Troubleshooting matrix
11. Test protocol
12. Definition of done

## 1. Packaging Contract

Compilation and distribution are separate proofs:

```text
source compiles
  != staged Workshop addon contains output
  != uploaded item contains output
  != downloaded client VPK contains output
  != server and client mount the same revision
  != runtime graph selects output
```

Track each stage explicitly. Do not diagnose animation curves while the client
reports `ERROR_FILEOPEN` for a graph, clip, model, material, or script.

The addon normally needs all transitive resources below the roots it uses:

```text
animation/
models/
materials/
scripts/                      # when custom VData or other scripts are used
panorama/images/icons/        # optional equipment icons
particles/                    # optional
soundevents/ and sounds/      # optional
```

Use source-relative paths in graph and model resources. Preserve case and path
normalization consistently even on Windows; the server and Workshop runtime can
be case-sensitive.

## 2. Packer Roots And Gameinfo

Workshop Tools decides which roots can enter the VPK through the addon's
configuration. In current builds this can involve `gameinfo.gi` under an
`AddonConfig` / `VpkDirectories` section. If `animation` is omitted, compiled
`.vnmgraph_c` and `.vnmclip_c` files can exist in the addon output yet never
enter the uploaded VPK.

A current observed directory-list shape is:

```text
"VpkDirectories"
{
    "include" "animation"
    "include" "models"
    "include" "materials"
    "include" "scripts"
    "include" "panorama/images/icons/equipment" // only when used
    "include" "particles"                       // only when used
}
```

Do not include all of `panorama` by default. Equipment icons are a distinct
packaging use case; custom Panorama layouts and scripts may enter a package but
current CS2 clients intentionally refuse to load them from ordinary Workshop
addons. Packaging is not proof of UI execution, item-definition registration,
or localization-token registration. Overriding a stock proxy's icon path also
affects that proxy wherever the addon is mounted; it is not per custom entity.

Do not copy this syntax blindly into another build. Compare the current file.
Editing an installed `gameinfo.gi` or packer configuration requires explicit
user approval. Use an offline copy or a reversible, dry-run-capable script that:

1. hashes and backs up the current configuration;
2. adds only missing managed lines;
3. reports the exact diff;
4. restores only those managed lines after upload;
5. refuses an unknown file layout.

Close and restart Workshop Tools after changing packer configuration. An editor
process can cache the previous directory list.

Do not treat modifications to the base `game/csgo` resource tree as Workshop
authoring. Keep normal authored and compiled assets in the addon's `content` and
`game/csgo_addons/<addon>` trees.

## 3. VPK Inspection

For initial integration or relevant packaging/mounting debugging, inspect
three artifacts when available:

```text
local compiled addon output
local staged/upload VPK
Steam-downloaded Workshop VPK
```

List all files and compare expected paths and hashes. At minimum verify:

```text
private first-person root and every child graph
private third-person root and every child graph
all canonical VNMClip resources
owner and world object VMDLs
player VMDL with private graph references
materials and textures
weapons.vdata_c, if used
equipment icon, if used
```

Detect ambiguous duplicates. Shipping both old and new action aliases is risky
even when only one appears to be routed; future patches or stale graph children
can select the wrong resource. Produce a package report such as:

```json
{
  "workshop_id": "<id>",
  "content_revision": "<timestamp-or-manifest-id>",
  "files": {
    "animation/<namespace>/<item>/viewmodel.vnmgraph_c": "sha256..."
  },
  "duplicates": [],
  "missing": []
}
```

Never delete unrelated addon assets while staging a focused update. Build from
an allowlisted manifest or merge generated outputs into the existing addon.
Before producing a distributable handoff, require an explicit `allowed`
artifact policy with a non-empty evidence basis that covers authored,
template-derived, and transitive inputs. A successful local compile does not
establish redistribution permission.

### Routine publication and source selection

When the user has already confirmed publication and agreed a deployment fast
path, do not require a new VPK asset audit on every iteration. Use the nominated
publication output, transfer it with transport integrity/revision evidence,
follow the instance's restart/rollback procedure and check runtime health.
Retain the existing asset-validation limits and inspect contents again when a
new symptom calls for it. This is a project/user agreement, not a global rule
that all publication confirmations authorize deployment.

Distinguish the publisher's output (observed under
`game/csgo_addons/vpks/<item-id>`) from a subscribed cache under
`steamapps/workshop/content/730/<item-id>`. They can contain different revisions.
Resolve the actual source from the publication receipt; file presence or an
older subscribed copy is not proof of the just-published upload. Manual client
base-game placement remains a separate, explicitly authorized action.

## 4. Server Mounting

The server and every client must mount the same Workshop item revision. The
exact launch option or framework API is server-stack-specific. Some community
setups use addon launch arguments such as `-dual_addon`; others use a Workshop
collection or plugin-managed mount. Verify the mechanism used by the current
server rather than copying an option from another stack.

During mounting diagnosis, test opening the exact resource through the
server's `GAME` search path using a supported read-only filesystem API and
close the handle. Precache success, `Resident`, or a mount log alone does not
prove this access. Confirm framework bindings against their actual native
operation if the results conflict. A client copy does not update the dedicated
cache. When both module and Workshop resource names change, activate their
matching revisions together after the affected instance is safe to restart.

For deployment:

1. record the Workshop item ID and downloaded revision;
2. verify the server has the current VPK or can download it;
3. update the instance configuration without exposing tokens;
4. restart the affected instance when required;
5. inspect startup logs for mount and resource errors;
6. reconnect a clean client after its download completes.

Do not test with a client-side loose copy as a substitute for server/Workshop
mounting. Loose copies can hide missing package roots and stale uploads.

## 5. Plugin Responsibilities

AnimGraph2 resources provide presentation logic. The server plugin provides
gameplay and lifecycle. A generic plugin may need to:

```text
mount or require the Workshop item through the server framework
precache models/resources when the current API requires it
give a native proxy weapon
mark that exact entity instance as the custom item
assign the world-object model; assign owner presentation only through a
verified current owner-composition contract
assign a player model whose private roots own 1P and 3P graphs
apply native presentation data through the proven client lookup contract;
use a new subclass identity only when its client registration is proven
manage charges/ammo and gameplay state
intercept or reinterpret native input safely
restore models/state on unequip, death, disconnect, map change, and unload
```

Use per-entity markers to scope server gameplay instead of replacing behavior
for every instance of the native proxy. This does not scope client animation:
while the private player model is active, every item exposing the same client
`weapon_type` selects the same graph branch. If a normal copy must remain stock,
enforce proxy exclusivity, restore the stock player model before activation, or
prove a different client-visible discriminator.

Conceptual server flow:

```text
give_custom_item(player):
    weapon = give_native_proxy(player)
    mark_instance(weapon, custom_item_id)
    apply_world_object_model(weapon)
    apply_compatible_player_model(player)
    initialize_gameplay_state(weapon)

on_command(player, command):
    weapon = active_weapon(player)
    if not marked_custom_instance(weapon):
        return
    process_edges_and_transaction(player, weapon, command)

on_lifecycle_change(player):
    cancel_pending_action(player)
    restore_player_model_when_no_custom_item_requires_it(player)
```

The plugin should not patch a client-only HUD AnimGraph controller, client DLL,
or process memory. First-person selection should come from mounted client
resources, client-visible weapon identity, and the player's `hudmodel` root.

Precache APIs, model setters, VData application, and pointer layouts are
framework- and build-dependent. Discover schema fields and validate current
behavior; do not make an old offset part of the generic skill.

## 6. VData And Client Identity

A custom subclass is a VData block that inherits from the stock item
definition key and overrides presentation fields (`m_szWorldModel`,
`m_szAnimSkeleton`, `m_szAnimClass`, ammo/cycle fields). Giving the subclass
name to the server's item creation sets the networked subclass id; the client
resolves it in its own `weapons.vdata_c`, which the addon must ship as the
complete stock file plus the additions (rebuild after every game update, and
verify the native blocks did not change). Compile the document with
`-fshallow` like any script resource. Until a clean client has been observed
resolving the subclass, route the stock proxy symbol in the private root as
the fallback.

Start from the current installed `weapons.vdata_c` reference when authoring a
profile. An old full-file copy can lose fields added by updates or override
current stock definitions. Prefer a minimal addon profile if the format and
mounting rules permit it.

Treat `scripts/weapons.vdata` as a canonical/global resource path unless a
current clean-client merge test proves otherwise. VPK presence or resource
residency does not prove a new key was registered. In proxy mode, do not replace
stock numeric records merely to manufacture a custom identity.

An intentional native-proxy presentation override is a different operation.
The measured M249 case changed model/AG2-model/skeleton fields under both `14`
and `weapon_m249`, preserving current gameplay fields and other stock records.
Its scope is addon-wide, not per marked server entity. The owner-view muzzle
vectors may also require a measured presentation update after reframing. See
[weapon-presentation-contracts.md](weapon-presentation-contracts.md) for those
contracts; none proves registration of a brand-new subclass.

Separate these concepts:

```text
native entity class        network/prediction implementation
server VData pointer       server instance behavior/data
client VData profile       local presentation data
client weapon_type         graph variation selector
AnimClass/name fields      inputs used by profile/selector logic
```

A successful server memory write proves only that the server entity points to a
VData object. It does not prove that the client registered or selected a custom
profile. Observe `weapon_type` on the HUD-arms graph.

In native proxy mode, preserve the proxy's client-visible identity and route
that stock symbol inside the private graph. This is often more reliable than
forcing a custom identity that the client cannot resolve.

When applying or cloning VData, preserve fields that own viewmodel composition
unless the custom architecture replaces the entire contract. In particular,
an inappropriate owner-only model field can suppress arms.

## 7. Input And Prediction

The client predicts native weapon input before the server receives the command.
The plugin must avoid fighting that prediction every tick.

Common failure pattern:

```text
client predicts native attack and enters an action
server removes attack, restores ammo, and forces cooldown every command
snapshot corrects the client
custom animation cancels, snaps, or restarts continuously
```

Use edges and a gameplay transaction:

```text
press edge:
  reserve one charge
  begin custom action once

held:
  advance server timer
  do not re-enter the graph state every command

release before completion:
  cancel action
  restore reserved charge if policy requires

completion:
  commit gameplay effect
  update authoritative count/ammo once
  return to idle
```

Give each action an incrementing token/generation. Timers, releases, and
completion callbacks must compare that token and become no-ops when stale. This
prevents duplicate commit/refund after switch, death, latency, or reconnect.

Block native effects at the narrowest reliable point. Avoid setting a permanent
far-future attack tick or rewriting clip/ammo values continuously unless the
current proxy and prediction behavior have been measured. Test latency, packet
loss, spectators, weapon switching, death, and reconnect.

For a multi-second visual action, the AnimGraph also needs a dedicated state
that does not exit on the proxy's short native fire-complete pulse. Server code
alone cannot keep a stock short attack state visually active.

Map `enter`, `hold`, `release/cancel`, and `complete` to parameters or events
actually observed on the client graph. If the proxy exposes no client-visible
release/cancel signal, the server can still cancel gameplay, but the visual may
have to finish; document that limitation instead of claiming synchronized early
cancellation.

## 8. Player Model Lifecycle

The custom player model may be required because it carries private `hudmodel`
and `worldmodel` roots. Apply it to the networked player pawn through the
current supported server API.

Resolve the final appearance after role and inventory/cosmetic selection. A
later cosmetic assignment can replace an earlier private-graph fallback. Use a
shared, exact role/model mapping to the graph-only variant, preserving cosmetic
identity and mesh/physics, and inspect the actual pawn path after all writers
have run. Do not repeatedly force the model to fight the appearance system.

Account for:

```text
initial give and spawn
team change
death and respawn
model replacement by another plugin
weapon switch and drop
disconnect/reconnect
map transition
plugin reload/unload
multiple custom items sharing one private player model
```

Some builds do not immediately rebuild owner-viewmodel composition after a
player model changes. A respawn, model rebind, or weapon re-equip may be needed.
Treat that as observed build behavior and encapsulate it; do not blindly force
respawns in a generic implementation.

Restore the previous player model only when no possible active identity still
depends on the private roots. Conversely, an ordinary instance sharing a custom
proxy symbol requires model restoration, another proven client-visible
discriminator, or explicit proxy exclusion before it becomes active.

## 9. Runtime Diagnostics

Enable developer output only on a private development server. Command names and
cheat requirements can change; verify them in the current build and restore the
server's normal cheat policy after testing.

Run cheat-protected/replicated controls from the server operator console:

```text
sv_cheats 1
animgraph_debug 1
```

Then configure the observing client:

```text
developer 1
r_showdebugoverlays 1
cl_ent_text_flags_active -1
animgraph_debug_set_filter_params weapon_type
animgraph_debug_show_unreferenced_params 1
animgraph_debug_variables 1
animgraph_debug_variables_ignore_nonchanges 0
cl_ent_animgraph_debug cs2_hudmodel_arms
animgraph_debug_entindex
```

The class selector can print several HUD-arms entities for the local player,
bots, spectators, previews, or stale presentation objects. Match the model path
and owner/context, then select the numeric entity index reported by the command:

```text
cl_ent_animgraph_debug <current-index>
```

Select only after the final spawn, player-model assignment, and weapon equip.
Respawn, reconnect, model replacement, or viewmodel reconstruction invalidates
old indices; rerun the class query instead of reusing a historical number. If
the text is hidden, confirm `r_showdebugoverlays`, the server-side
`animgraph_debug`, and the current entity selection before changing assets.

Clean up after the probe:

```text
cl_ent_clear_debug_overlays
cl_ent_text_sticky_clear
r_showdebugoverlays 0
developer 0

server operator:
animgraph_debug 0
sv_cheats 0   // only when this restores the server's prior policy
```

The objective is to observe, not assume:

```text
HUD-arms entity exists
player/arms model path
active first-person root
client weapon_type
active state/action and clip
third-person pawn model and root
resource load errors
```

Build a plugin debug command that prints concise console-only diagnostics for
the exact marked item instance:

```text
entity handle including serial/generation, current index, native classname,
and custom-archetype marker
owner and active-weapon match
server VData identity, when used
owner/world model paths
player model path
gameplay state and reserved charge
expected client identity and private roots
Workshop revision expected by the server
```

Do not flood player chat or server logs every command tick. Use one-shot dumps,
rate-limited transitions, and a toggleable verbose mode.

### Evidence labels

Use the canonical labels from `SKILL.md`; do not introduce aliases for the same
stage:

```text
static-observed
source-authored / generated
roundtrip-valid (optional DMX serialization evidence)
compiled
inspected
packaged
downloaded-vpk-inspected
mounted
route-proven
first-person-validated
third-person-validated
gameplay-validated
in-game-validated
```

`inspected` means semantic inspection of the compiled resource, not merely file
existence. `in-game-validated` requires every applicable first-person,
third-person, and gameplay validation; never report `working` when only
`compiled` is proven.

Keep an evidence matrix instead of merging independent claims:

| Claim | Minimum evidence |
|---|---|
| first-person route | local HUD-arms model/root, identity, active state/clip, visible result |
| third-person route | separate observer/bot view of pawn root, character motion, held object |
| custom VData identity | clean client reports the custom profile and exact custom `weapon_type` |
| current-build compatibility | rerun package, route, owner, observer, and regression tests after update |

## 10. Troubleshooting Matrix

| Symptom | Check first | Typical cause |
|---|---|---|
| `ERROR_FILEOPEN` for custom graph/clip/model | Downloaded VPK file list | Missing packer root, wrong path/case, stale upload, unmounted item |
| Custom world object but stock first-person hands | HUD-arms model/root and `weapon_type` | Player `hudmodel` still stock |
| Floating item with no arms | Player bodygroup, owner composition, IK | Weapon-only owner model used where full viewmodel expected, or broken player route |
| Stock gun appears after switch/reconnect | Exact entity model/VData lifecycle | Model assignment applied only once or to stale entity |
| Sentinel idle works but attack stays stock | Action child dependencies/state | Only idle variation was patched |
| 1P custom, 3P stock | Player default/named worldmodel roots | No private third-person graph or locomotion branch |
| 3P object custom, character pose stock | Pawn graph versus held model | Only world object VMDL changed |
| Hands collapse or disappear | Final IK and skeleton basis | Broken `wpnHand_L/R`, wrong rest transforms, wrong skeleton |
| Clip is valid in viewer but outside camera in game | Graph overlays/IK and export basis | Remaining stock layer, basis mismatch, or incorrect root transforms |
| Long action begins then immediately returns idle | State transition logic and prediction | Stock short attack exit still active |
| Holding input restarts action forever | Edge handling | Press logic executed every tick |
| Release waits for full animation | Explicit cancel transition | Graph has completion-only exit |
| Custom `weapon_type` never appears | Client VData registration | Only server VData was changed |
| Local loose test works, Workshop does not | Clean client and downloaded VPK | Missing package dependency hidden by base-tree files |
| ResourceCompiler has no Nm compiler | Current asset-type registrations | Steam/tool repair removed hidden registration |

Additional symptoms recorded on build 2000899:

```text
arms and weapon absent, camera looks at nothing, clip compiled without warning
  -> the clip DMX is in raw Source axes (VRF <= 19.1 decompile) instead of
     the compiler frame; re-export with the conversion (authoring reference,
     "DMX frame")

custom arms play but the weapon's own parts (slide, pin, inner object) stay
  -> inspect the compiled secondary animation and skeleton match; if absent,
     add weapon joints/channels under the measured DMX export parent and list
     the skeleton in the document; runtime wpn does not dictate DMX parenting

three custom items on one native proxy all show the same clips
  -> the client reports the stock weapon_type; only a subclass with its own
     m_szAnimClass, resolved by the client's weapons.vdata, can distinguish
     them (or use one private root per player model)
```

For a correctly loaded model with a misplaced muzzle, missing charge, rotor
snap or silent/duplicated motor audio, use
[weapon-presentation-contracts.md](weapon-presentation-contracts.md). Sound-bank
string paths may need explicit raw-sound package/precache roots, and missing
projectile attachments require model changes rather than another precache call.

## 11. Test Protocol

### Packaging preflight

1. verify the artifact policy and its recorded redistribution basis;
2. compile from untouched authorized project sources;
3. inspect all compiled resources;
4. compare the exact full output set to the allowlisted manifest;
5. build/upload without deleting unrelated addon assets;
6. inspect the uploaded or staged VPK;
7. wait for/download the Workshop revision;
8. inspect the downloaded VPK and compare hashes;
9. confirm the server expects the same Workshop revision.

### Clean first-person test

1. remove only explicitly approved loose test copies;
2. start CS2 normally with the Workshop item mounted;
3. reconnect or restart after a Workshop update;
4. give the marked native proxy;
5. observe HUD-arms model, root, and `weapon_type`;
6. test draw, idle, primary action, cancel, inspect, switch, drop, death, and
   respawn;
7. test at least two aspect ratios/FOV settings if camera framing matters.

### Third-person test

Use another client, spectator, or bot observer. Test standing, crouching,
movement, action, cancellation, weapon switching, death/ragdoll, dropped item,
and reconnect. A local first-person shadow is useful evidence but is not a full
observer test.

### Regression test

Test custom proxy -> ordinary same-class proxy -> unrelated stock -> custom.
Confirm ordinary proxy instances and unrelated players keep stock models,
graphs, input, and animations, or verify that documented proxy exclusivity is
actively enforced.

## 12. Definition Of Done

Use the single [Completion Contract](../SKILL.md#completion-contract) in
`SKILL.md` as the release gate. This runtime reference supplies the evidence for
that gate; it does not define a second checklist. Preserve at least these
runtime-specific evidence bundles:

- downloaded-VPK hashes plus matching client/server mounted revisions;
- HUD-arms model, private root, identity, selected branch, and action traces;
- first-person, third-person, gameplay, cancellation, latency, death,
  reconnect, and clean observer results;
- same-proxy stock and unrelated-player negative controls;
- proof that no loose base-game file was required for the result.

Keep testing on a private/community development server. Do not ship debug
commands that weaken production security, and do not redistribute Valve-owned
reference assets in a public skill or repository.
