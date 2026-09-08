# Graph Routing And Patching

Use this reference to design private AnimGraph2 roots, route client-visible
weapon identities, patch source or compiled graphs, and support first-person and
third-person actions.

## Contents

1. Selection architecture
2. Identity strategy
3. Private graph families
4. First-person graph contract
5. Third-person graph contract
6. Source graph editing
7. Compiled graph patching
8. IK and pose integrity
9. Long-running actions and cancellation
10. Sentinel routing proof
11. Multiple custom items
12. Graph review checklist

## 1. Selection Architecture

AnimGraph2 success depends on which client entity owns the graph and which
parameters that client resolves. A custom clip on disk is inert until a mounted
graph instance selects it.

First-person selection commonly follows this chain:

```text
local weapon VData
  -> client-resolved weapon_type
  -> local player's ModelDoc entry named hudmodel
  -> private viewmodel root
  -> category/action child
  -> variation matching weapon_type
  -> VNMClip authored for viewmodel.vnmskel
```

Third-person selection commonly follows this chain:

```text
networked player model
  -> default and/or named worldmodel AnimGraph2 reference
  -> private worldmodel root
  -> locomotion/category and weapon action children
  -> variation matching weapon_type
  -> full-character VNMClip authored for worldmodel.vnmskel

weapon entity/VData
  -> separate held-object world VMDL
```

The held object and the character pose are independent. Seeing the custom item
in an observer's hand does not prove that the player worldmodel graph changed.

Likewise, an owner VMDL does not select the HUD-arms graph. The player model's
`hudmodel` reference can remain stock even while a custom object is visible.

## 2. Identity Strategy

### Native proxy mode

For a server plugin plus Workshop addon, default to a native predicted weapon as
the network proxy:

```text
entity classname       native stock class
client weapon_type     stock symbol observed for that class/profile
private graph branch   handles that exact stock symbol
custom gameplay        implemented by the server plugin
```

This is intentionally different from pretending that a new client weapon class
exists. A server-only VData clone or memory pointer does not create a client
schema class, serializer, prediction implementation, or locally registered
`weapon_type`.

The native proxy and the animation reference do not need to be the same stock
item. For example, a pistol can remain the network proxy while C4 or grenade
clips serve as pose references. The private graph still has to route the exact
identity observed by the client.

Per-entity markers can isolate server gameplay, but the private client graph
cannot see them. While a private player model is active, an ordinary stock item
with the same client `weapon_type` selects the same custom branch. Require one
of these policies and record it in the route manifest:

```text
proxy exclusivity: do not allow an ordinary same-class proxy concurrently
model restoration: restore the stock player model before that proxy is active
client discriminator: use another value only after observing it in the graph
```

### Custom VData mode

Use a custom VData profile only when all of the following are proven on the
client:

1. the downloaded Workshop VPK contains the current `weapons.vdata_c`;
2. the addon mount makes the profile discoverable;
3. the local weapon resolves the intended custom profile;
4. AnimGraph debug reports the intended custom `weapon_type`;
5. reconnect and clean-client tests reproduce the result.

If any step fails, route the stock proxy symbol in the private graph instead.

Do not confuse `m_szAnimClass`, `_class`, a VData key, and `weapon_type`.
Inspect current resources and observe runtime values.

Measured on build 2000899 in the shared weapon graph controller code
(`ReflectWeaponState`, read from the server binary): `weapon_type` equals
the VData `m_szAnimClass` when it is set, otherwise the VData `m_szName`;
`weapon_category` comes from `m_WeaponType`. A subclass that inherits from an
item definition therefore reports the stock `weapon_type` unless it declares
its own anim class, and a declared anim class must be routed by a private
root because the stock roots have no variation for it. The subclass travels
to the client as the networked subclass id and is resolved in the client's
own (addon-shadowed) `weapons.vdata`; keep the full stock file plus your
additions and rebuild it after every game update. Player pawn and HUD-arms
graph parameters are recomputed on the client from networked state; server
AnimGraph2 parameter writes only drive server-owned entities (NPCs, props).

## 3. Private Graph Families

Never publish replacements at Valve's shared graph paths. Create a unique root
and private descendants:

```text
animation/<namespace>/<item>/
  viewmodel.vnmgraph
  viewmodel_gun.vnmgraph
  viewmodel_gun.vnmgraph+<proxy-variation>.vnmgraph
  viewmodel_inspects.vnmgraph
  viewmodel_inspects.vnmgraph+<proxy-variation>.vnmgraph

  worldmodel.vnmgraph
  worldmodel_gun.vnmgraph
  worldmodel_gun.vnmgraph+<proxy-variation>.vnmgraph
  worldmodel_locomotion.vnmgraph
  worldmodel_locomotion.vnmgraph+<category>.vnmgraph
```

The actual child names differ by build and stock reference. Mirror the current
dependency shape, then redirect references inside the private namespace.

Benefits of private roots:

- no Valve-global path override; effects are limited to actors using the
  private player root, not automatically to one weapon entity;
- multiple custom items can coexist;
- binary patches remain scoped and reviewable;
- Workshop updates cannot silently shadow a Valve path for every client;
- stock and custom behavior can be compared in the same session.

Keep a route manifest:

```yaml
player_model: models/<namespace>/<agent>.vmdl
hudmodel_root: animation/<namespace>/<item>/viewmodel.vnmgraph
worldmodel_root: animation/<namespace>/<item>/worldmodel.vnmgraph
client_weapon_type: <exact-runtime-observed-symbol>
variation_suffix: <observed-current-suffix>
actions:
  idle: models/<namespace>/<item>/clips/idle_<item>.vnmclip
  draw: models/<namespace>/<item>/clips/draw_<item>.vnmclip
  primary: models/<namespace>/<item>/clips/primary_<item>.vnmclip
```

### Variations live in the parent document

A `+<variation>` graph is not a separate source file. The parent document
declares its variations in `m_variationHierarchy.m_variations` (id, parent
id, skeleton) and every clip or referenced-graph node carries per-variation
`m_overrides` (`m_variationID` + the node data with the clip or graph path).
Compiling the parent emits `<parent>.vnmgraph+<id>.vnmgraph_c` for each
declared variation, so a private parent copy that adds one variation also
emits every stock variation; delete those from the package. To add an item:
clone the overrides of the closest stock variation, map each resource to the
private clip set, add the variation entry, and extend the root's ID
comparison lists (`m_values` of the `CNmGraphDocIDComparisonNode`) with the
new `weapon_type`; several ids can share one state.

## 4. First-Person Graph Contract

The graph instance to inspect is the local HUD-arms entity, commonly named
`cs2_hudmodel_arms` in current debug output. Do not assume the weapon entity's
server AnimGraph controller drives this client-only presentation.

A private viewmodel family must preserve the stock controls that CS2 supplies,
including relevant action, category, deploy, attack, reload, inspect, and hand
IK parameters. Remove or rename a parameter only after proving all call sites.

The player model must expose the private root through its named `hudmodel`
AnimGraph2 reference. A custom owner weapon model without that player route can
still use stock hand poses.

The variation comparison must match the client-observed `weapon_type`. In proxy
mode, retaining the stock variation name is normally correct even when the mesh
and gameplay are custom.

### Server-driven action triggers

The client only reacts to networked state, so a "spell" or custom action is a
normal weapon or pawn state change that the private graph reinterprets:

| server writes | client parameter | stock meaning | custom use |
|---|---|---|---|
| a subclass weapon with its own `m_szAnimClass` | `weapon_type`, `weapon_category` | weapon family | a spell weapon whose idle/draw/attack states are the spell |
| current-build weapon gameplay animation state plus fixed phase-start timestamp | native action dispatch into the private Reload branch | reload presentation token | charge/cast clip where the native reader and proxy contract are proven; gate attacks separately |
| `m_bSilencerOn` toggle (weapons with a silencer type) | `action_silencer_attach/detach` | silencer | a second distinct action slot |
| pawn `m_bIsDefusing` | `is_defusing` (third person) | kneel on bomb | rooted channelled pose |
| hit-reaction netvars | flinch layers | flinch | additive impact layers (noisy) |

On the inspected M249 client (2000905), `m_bInReload` plus an attack delay
alone did not establish the Reload animation action. The server used the
framework's named gameplay-animation state and a fixed timestamp while keeping
ammo-reload state separate. Prediction, completion and cancellation still need
runtime checks; do not infer them from the existence of a network field. See
[weapon-presentation-contracts.md](weapon-presentation-contracts.md) for that
build-scoped case, agent selection, grip fitting and secondary-root diagnostics.

Native grenade flow is a good example of "nothing to send": pressing attack
enters Charge (pull pin), holding blends the throw-charge poses by
`attack_throw_strength`, releasing enters Throw (`attack_type` picks overhand
or underhand). A private variation that replaces those clips needs no server
change at all; only the weapon model and, if wanted, the subclass identity are
server decisions.

## 5. Third-Person Graph Contract

Third-person needs a private worldmodel root and full-character clips. Do not
reuse first-person `viewmodel.vnmskel` clips in a graph that expects
`worldmodel.vnmskel`.

Route both the player's default graph and named `worldmodel` reference when the
current stock ModelDoc uses both. They are parallel contracts, not aliases that
can always be inferred from one another.

Changing only the weapon action child can leave stock standing, crouching,
turning, and locomotion poses. Inspect and, where necessary, recreate in
original source or derive locally under the source/patching rules below:

```text
weapon action variation
standing/crouching locomotion category
draw/equip transitions
primary-action transitions
movement overlays and additive layers
```

Use a complete test matrix:

```text
standing idle
crouching idle
walk/run in several directions
draw and holster
primary action and cancellation
jump/land if the item remains equipped
death and ragdoll transition
observer join/reconnect
```

The custom world held-object VMDL must be tested separately for attachment,
origin, scale, and dropped state.

## 6. Source Graph Editing

Editable graph source is the preferred route.

1. Use a current stock graph as a read-only local structural reference.
2. Recreate the required control/routing contract in original private source.
3. If exact derivative material is unavoidable locally, generate it from the
   user's own hash-gated installation and exclude it from public outputs.
4. Redirect every descendant resource to the private namespace.
5. Keep parameter names and expected types unless intentionally changing logic.
6. Change one route or state at a time.
7. Compile children before parents.
8. Inspect the compiled dependencies and serialized strings.
9. Prove the route with per-action sentinel clips before polishing motion.

When Workshop Tools exposes the graph editor, use it to inspect state-machine
transitions and node wiring. Headless ResourceCompiler can compile Nm documents
once the current build has the required asset-type registrations.

Do not assume a graph recompiles correctly because its source editor can open
it. Inspect the resulting `.vnmgraph_c` and runtime selection.

### Worked example: the stock grenade family (build 2000899)

`viewmodel_grenade.vnmgraph` is one parent with the variations `decoy`,
`flash`, `he`, `incendiary`, `molotov`, `smoke`. Its state machine:

```text
Deploying                      clip node "deploy" (draw)
Idle                           clip node "idle" (looping), WPN_STATE_IDLE
Attack
  Charge                       clip node "pull_pin"; leaves on WPN_ACTION_COMPLETE
                               (time remaining <= 0.2 s)
  ReadyToThrow                 Blend 1D on attack_throw_strength between three
                               AnimationPoseNodes (throwcharge low / mid / high,
                               single-frame clips)
  Throw -> Overhand/Underhand  clip nodes chosen by attack_type
Inspect                        referenced graph viewmodel_inspects.vnmgraph+<id>_grenade
```

Clip events carry the gameplay sync points: `WPN_GRENADE_PULL_PIN` on frame
index 12 of the pull-pin clip, `WPN_GRENADE_THROW` on index 13 (overhand)
and 12 (underhand) of the throw clips, plus client-only sound events. A
replacement clip set keeps the same event indices and durations so the
native throw timing still matches what the player sees. During the throw the
stock clips park `wpn` behind the camera; the visible grenade position comes
from the weapon skeleton's secondary animation until the release.

## 7. Compiled Graph Patching

Binary patching is a fallback when source compilation is unavailable or a
private graph must be derived from a compiled current graph. It is not a global
search-and-replace task.

Patch only an offline copy of a resource owned or legally obtained by the user.
In this skill, "binary patching" never means modifying CS2 DLLs, a running
client, process memory, anti-cheat behavior, or network trust boundaries. Do not
publish Valve-extracted or byte-patched resources unless redistribution rights
are established; prefer an original graph source or a local patch recipe that
consumes the user's own hash-gated input.

### Required patch surfaces

A complete patch may need to update all references represented in:

```text
visible serialized strings
RERL external-resource entries
RED2/edit-info dependency entries
DATA block strings or serialized node data
raw ResourceId_t values
```

Changing a readable path while leaving its resource ID unchanged can produce a
graph that looks patched in a strings scan but still loads the original child
or fails to resolve the new resource.

Do not prescribe a ResourceId algorithm or seed as a timeless constant. A
patcher may use one only after validating multiple known path/ID pairs from the
exact target build and recording its algorithm, seed, path normalization,
extension handling, byte order, target hash, and regression vectors. Refuse to
patch when any check differs.

### Safe patch manifest

Use a machine-readable manifest rather than anonymous byte replacements:

```yaml
source_file: <private-copy-of-current-graph.vnmgraph_c>
source_sha256: <required-hash>
game_revision: <revision>
replacements:
  - old_path: animation/.../old_child.vnmgraph
    new_path: animation/<namespace>/.../new_child.vnmgraph
    expected_occurrences:
      strings: 1
      rerl: 1
      red2: 1
      data: 1
      resource_id: 1
output_path: animation/<namespace>/<item>/viewmodel.vnmgraph_c
```

The patcher must refuse unknown source hashes, unexpected occurrence counts,
overlapping edits, invalid section bounds, and unresolved dependencies.

Same-length string substitution is useful for a proof of concept because it
avoids relocating sections, but it does not remove the need to update hashes
and every reference surface. Production patchers should parse the current
resource format and rebuild tables rather than assume eternal offsets.

Never document a fixed binary offset as a permanent API. Record offsets only as
evidence tied to an exact binary hash and revision.

## 8. IK And Pose Integrity

Preserve the stock final hand-IK topology. Current reference graphs commonly
target helpers such as:

```text
wpnHand_L
wpnHand_R
```

Do not change those targets to `hand_L` or `hand_R` self-targets. A self-target
can create feedback, collapsed arms, or missing geometry. Keep the reference
constraints, helper transforms, and blend order while proving custom clips.

Animation data and graph IK can both move the hands. If the compiled clip looks
correct in isolation but the in-game pose is wrong:

1. inspect the final graph IK targets;
2. inspect whether a stock overlay remains active;
3. verify action/category state and blend weights;
4. check that the weapon helper skeleton matches the clip;
5. compare the HUD-arms graph pose before and after final IK.

Do not compensate for an incorrect basis or graph route by pushing hands far
away in Blender. Fix the contract that introduced the error.

## 9. Long-Running Actions And Cancellation

Stock gun graphs often enter an attack state on a brief action impulse, then
leave when the action returns to idle or a native completion event fires. A
multi-second custom action needs its own state rather than a longer clip dropped
into a short stock state.

First inventory which graph parameters/events are actually client-visible for
the chosen proxy. Design a dedicated state only around observed signals:

```text
attack edge
  -> Start (non-looping)
  -> optional Hold (looping only when needed)
  -> Finish or Cancel (non-looping)
  -> Idle
```

A completion transition must observe a non-looping pose. Do not wait for clip
completion on a looping node.

The state's exit conditions should be based on the custom clip/state lifetime,
not on stock ammo correction, stock fire-complete events, or the immediate
return of the proxy's action parameter to idle.

Do not invent a `TimeRemaining`, `StateCompleted`, or similarly named query from
an old decompile. Match a completion topology in a current stock graph, verify
the node type and reset semantics, then validate it in a private probe. Treat a
feedback-loop or crash claim as build-specific until reproduced with exact
resource hashes.

Write a transition table before implementation. Every visual transition must
name the graph signal the client observes; every gameplay transition must name
the authoritative server event:

| Transition | Server event | Client-visible graph signal | Fallback |
|---|---|---|---|
| enter | press edge | observed attack/action edge | reject action |
| hold | timer/token remains active | latched graph state or local clip lifetime | do not retrigger |
| release/cancel | release, switch, death, invalid target | observed cancel/invalidation parameter or state | visual may finish; cancel gameplay |
| complete | matching action token reaches deadline/effect | local state/clip completion or observed completion event | server commit remains authoritative |

If no client-visible release/cancel signal exists, do not claim early visual
cancellation. Let the visual state finish safely while the server cancels the
gameplay transaction.

Coordinate server gameplay using an idempotent action-generation token so a
stale timer or duplicate command cannot commit or refund twice:

```text
input edge -> create token, begin visual state, reserve gameplay resource once
hold       -> keep token; do not retrigger the entry every tick
release    -> invalidate token; restore reservation at most once
complete   -> commit only the current token; return to idle
```

The graph and server need not share an unsafe memory controller. They do need
compatible network-visible state transitions and timing.

## 10. Sentinel Routing Proof

Before evaluating animation quality, patch and test one action at a time, or
route every intended action to a different obvious diagnostic pose/clip. A
single always-active idle sentinel can overlay the other states and create a
false proof. Choose poses that cannot be mistaken for stock or for each other.

Test each action independently after a clean Workshop mount. For each test,
require both the expected sentinel and debug evidence for the exact active state
and clip:

```text
draw
idle
primary action
secondary action, if used
reload, if used
inspect
```

Require every one-shot sentinel to return to the unique idle sentinel. Include
an ordinary same-proxy instance and an unrelated actor as negative controls.

Interpret results:

| Result | Likely conclusion |
|---|---|
| Every action shows its own expected sentinel and active clip | Root, identity, variations, and action children are routed |
| Only idle changes | Attack/deploy/inspect child graphs still use stock paths or logic |
| Custom object, stock hands | Owner model changed but HUD player graph did not |
| Floating object, no arms | Player/bodygroup/owner composition or IK contract is broken |
| No visible change | Wrong player root, client identity, variation, package, or mount |
| Resource-open errors | Missing VPK path/dependency; do not debug Blender yet |

Once routing is proven, replace one action at a time with its real clip and
retain the sentinel as a reusable regression test outside the shipping route.

## 11. Multiple Custom Items

One custom player model can host a shared private root that dispatches several
client-visible identities to separate private item families:

```text
private player root
  weapon_type == proxy_A -> item_A variation
  weapon_type == proxy_B -> item_B variation
  otherwise              -> private stock-compatible fallback
```

Do not require one player model per item unless the build's graph ownership or
bodygroup composition makes that necessary. Conversely, do not route two
custom items through the same stock proxy symbol without another client-visible
discriminator; the graph cannot infer server-only intent.

Also test the ordinary stock instance of every reused proxy. If it must remain
stock, enforce proxy exclusivity or restore the stock player model before it is
active; a server-only item marker cannot change the client branch.

Maintain unique namespaces and canonical action paths for each item. Verify
switching A -> B -> stock -> A, death, reconnect, and observer behavior.

## 12. Graph Review Checklist

Before packaging, verify:

- [ ] all roots and descendants use the private namespace;
- [ ] the player ModelDoc references the private first- and third-person roots;
- [ ] the compared identity equals the runtime client `weapon_type`;
- [ ] viewmodel clips use the first-person skeleton;
- [ ] worldmodel clips use the full-character skeleton;
- [ ] weapon/action and locomotion/category third-person branches are covered;
- [ ] final `wpnHand_L/R` IK topology remains valid;
- [ ] every action has one canonical clip path;
- [ ] long actions map every transition to an observed client signal and an
      idempotent server action token;
- [ ] compiled graphs contain the intended paths and resource IDs;
- [ ] no Valve global graph path is overwritten;
- [ ] per-action sentinel routes and active-clip evidence passed before
      animation-quality review;
- [ ] ordinary same-class proxy regression or enforced exclusivity passed.
