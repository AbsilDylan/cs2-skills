# Reading A Compiled AnimGraph2 Graph

## Contents

- [Goal](#goal)
- [Obtain A Text Representation](#obtain-a-text-representation)
- [Read The Top-Level Contract](#read-the-top-level-contract)
- [Recover Control Parameter Types](#recover-control-parameter-types)
- [Follow Conditions And Transitions](#follow-conditions-and-transitions)
- [Map Clips And Timing](#map-clips-and-timing)
- [Build A Parameter Contract](#build-a-parameter-contract)
- [Trooper Case Study](#trooper-case-study)
- [Common Analysis Errors](#common-analysis-errors)

## Goal

Treat the graph as an executable contract, not a list of animation names. Before writing NPC logic, recover:

- every externally controlled parameter;
- its exact Bool, Float, ID, Vector, or Target type;
- accepted ID values and meaningful numeric thresholds;
- state-machine transitions and action pulses;
- clip resources, loop flags, events, and timing;
- skeleton, secondary skeleton, referenced graph, and external slot dependencies.

Keep the decompiled output local. It may contain third-party or Valve data that must not be published with the skill.

## Obtain A Text Representation

Use a current Source 2 resource viewer that can decompile `.vnmgraph_c` to text
or KV3. One historically observed CLI shape is:

```powershell
Source2Viewer-CLI.exe `
  -i path\to\npc_graph.vnmgraph_c `
  -o .local\graph-inspection\npc_graph.vnmgraph `
  -d
```

Tool flags can change; verify the installed CLI's help. Preserve the original compiled file hash and tool version in the local report.

Generate a first-pass summary from this skill:

```powershell
$SkillRoot = (Resolve-Path "<installed-cs2-ag2-npc-runtime-skill>").Path
$Graph = (Resolve-Path ".local\graph-inspection\npc_graph.vnmgraph").Path
python -B (Join-Path $SkillRoot "scripts\summarize_vnmgraph.py") $Graph
python -B (Join-Path $SkillRoot "scripts\summarize_vnmgraph.py") $Graph --format json
```

Resolve `$SkillRoot` from the installed skill location; do not assume the
workspace current directory contains the skill's `scripts` folder.

The helper accepts only a generic, compiled-definition-shaped decompile. It
fails closed on empty/editor-shaped inputs, malformed arrays that it consumes,
duplicate or dangling node indexes, invalid roots/resource slots, and
unsupported control-node classes. It also enforces paired virtual-parameter
tables and the currently supported referenced-graph, external-graph, and
external-pose slot field shapes; an unfamiliar slot shape is refused instead
of guessed. Other optional tables and nested event semantics remain outside its
first-pass contract. This structural check does not prove the file's provenance;
preserve the compiled input hash and decompiler receipt. The helper reports
structure rather than pretending to reconstruct all graph semantics, so verify
decisive branches in the source text.

## Read The Top-Level Contract

Locate these fields first:

| Field | Meaning |
|---|---|
| `m_variationID` | Graph variation identity |
| `m_skeleton` | Primary skeleton resource |
| `m_supportedSecondarySkeletons` | Additional compatible skeletons |
| `m_nRootNodeIdx` | Root evaluation node |
| `m_controlParameterIDs` | Ordered external control names |
| `m_virtualParameterIDs` | Internally computed parameters |
| `m_referencedGraphSlots` | Referenced graph dependencies |
| `m_externalGraphSlots` | Graphs supplied from outside |
| `m_externalPoseSlots` | Poses supplied from outside |
| `m_nodePaths` | Human-readable path for each node index |
| `m_resources` | Ordered clip/resource data slots |
| `m_nodes` | Node definitions and their edges |

Do not assume a name in `m_nodePaths` is externally writable. The authoritative writable list is `m_controlParameterIDs` plus the corresponding control node definitions.

## Recover Control Parameter Types

Parameter order is significant. For each entry at index `i` in
`m_controlParameterIDs`, find the control parameter node associated with that
index. Its class is the type:

```text
CNmControlParameterBoolNode::CDefinition  -> Bool
CNmControlParameterFloatNode::CDefinition -> Float
CNmControlParameterIDNode::CDefinition    -> ID
CNmControlParameterVectorNode::CDefinition -> Vector
CNmControlParameterTargetNode::CDefinition -> Target
```

Never infer type from a name. `base_action` is commonly an ID, while `action_shoot` is commonly a Bool. Passing a Float to a Bool setter can silently fail or corrupt an unmanaged call contract. The bundled Linux bridge has only proven Bool, Float, and ID writes; detecting a Vector or Target does not authorize writing it.

The bundled helper deliberately accepts only the compiled layout where control
parameter `i` is node `i`; it checks the node class and uses `m_nodePaths[i]` as
a readable cross-check. If a current graph stores controls elsewhere, the
helper refuses it rather than guessing. Associate those controls manually from
the current decompile and record that unsupported layout before extending the
parser. Never infer a type from `m_nodePaths` alone.

## Follow Conditions And Transitions

Search for every reference to the control node index. Important edges include:

- `m_nInputValueNodeIdx`
- `m_nInputParameterNodeIdx`
- `m_nInputParameterNodeIdx0` and numbered variants
- `m_nConditionNodeIdx`
- `m_conditionNodeIndices`
- state-machine transition condition arrays

Then classify the consumer:

| Node family | Evidence to extract |
|---|---|
| `CNmFloatComparisonNode` | comparison operator and `m_flComparisonValue` |
| `CNmIDComparisonNode` | `m_comparisionIDs` values and match mode |
| `CNmIDToFloatNode` | `m_IDs` to `m_values` mapping |
| Bool control used directly | true/false transition meaning |
| `Not`, `And`, `Or` nodes | composed transition logic |
| state machine transition | source, destination, condition, blend, duration |
| selector or variation node | which parameter selects which branch |

Search direct condition indexes too. A Bool action can be referenced as `m_nConditionNodeIdx = 5` without appearing as an `m_nInputValueNodeIdx = 5` edge.

For ID parameters, record only exact values observed in graph data. Preserve spelling and case. An ID is normally passed through an engine symbol/string-token conversion, not as an arbitrary managed enum integer.

## Map Clips And Timing

For each clip node, recover:

- node index and `m_nodePaths[index]`;
- `m_nDataSlotIdx` and `m_resources[dataSlot]`;
- `m_bAllowLooping`;
- playback-speed input or multiplier;
- graph events and event percentages/times;
- transition blend and synchronization behavior.

This distinguishes three different timelines:

1. **Gameplay timeline:** when the server applies damage or launches a projectile.
2. **Graph timeline:** when the state enters, loops, or exits.
3. **Clip timeline:** when a muzzle, foot contact, or impact event occurs.

Align gameplay to a graph event when the server can observe it reliably. Otherwise document the measured clip offset and schedule from a one-shot state entry. Do not restart the one-shot every update.

Include all reachable clip families. Directional locomotion, target/no-target variants, turn clips, jumps, landings, hit reactions, attack variants, and death clips are often separate resources.

## Build A Parameter Contract

Create a table before coding:

| Name | Type | Valid values/range | Semantic | Write cadence | Bridge support | Evidence |
|---|---|---|---|---|---|---|
| `move_speed` | Float | `>= 0` | horizontal speed gate | continuous | requires matching build profile and receipt | graph comparison |
| `action_shoot` | Bool | pulse | enter shoot action | state entry | requires matching build profile and receipt | direct condition |
| `pivot_turn` | ID | graph-defined IDs | turn selector | on change | requires matching build profile and receipt | ID comparison |
| `target` | Target | graph-defined target payload | aim/IK target | continuous | diagnostic-only; writes unsupported until independently proven | control node class |

Also create an action table:

| Behavior event | Graph writes | Clear condition | Gameplay synchronization |
|---|---|---|---|
| Start moving | local speed parameters | velocity returns to zero | immediate |
| Shoot | target data, then action pulse | next update or acknowledged transition | muzzle event/offset |
| Die | health/death action | never return to locomotion | remove after death clip |

## Unverified Trooper-Shaped Example

The following list came from an unversioned historical note. No model path,
game build, resource hash, or decompiler receipt is bundled, so its evidence
label is **unverified**. Use it only to illustrate the extraction table shape;
never use it as an NPC runtime contract or a universal CS2 schema:

| Index | Name | Type | Typical role |
|---:|---|---|---|
| 0 | `in_air` | Bool | airborne selector |
| 1 | `has_target` | Bool | aimed vs unaimed branches |
| 2 | `action_melee` | Bool | melee action pulse |
| 3 | `look_heading` | Float | horizontal aim offset |
| 4 | `look_pitch` | Float | vertical aim offset |
| 5 | `action_shoot` | Bool | ranged action pulse |
| 6 | `time_scale` | Float | root playback scale |
| 7 | `health_percent` | Float | health-dependent branches |
| 8 | `strafe_speed` | Float | local right-axis velocity |
| 9 | `move_speed` | Float | horizontal speed magnitude |
| 10 | `random_seed` | Float | deterministic variation input |
| 11 | `pivot_turn` | ID | turn direction/angle selector |
| 12 | `forward_speed` | Float | local forward-axis velocity |
| 13 | `explosion_react` | Bool | explosion reaction pulse |
| 14 | `explosion_react_random_time_scale` | Float | reaction variation |
| 15 | `flinch` | ID | directional flinch selector |
| 16 | `action_kill` | Bool | kill action pulse |
| 17 | `action_heal` | Bool | heal action pulse |
| 18 | `random_variant` | Float | clip variation |
| 19 | `vertical_speed` | Float | vertical locomotion input |
| 20 | `base_action` | ID | broad action selector |

The same note listed `e_Turn_left_90`, `e_Turn_right_90`, `back`, `right`,
`left`, and `ground_jump`, but did not bind those values to `pivot_turn`,
`flinch`, or `base_action`. Treat every value-to-parameter association as
unknown until recovered from the actual graph being integrated.

The note also described target/no-target directional run families, turns,
jump/land states, hit reactions, melee, shoot, flinch, and aim behavior. This
illustrates why packaging only guessed `idle`, `run`, and `attack` clips can be
incomplete; it is not evidence that a new graph contains those families.

## Common Analysis Errors

- Guessing parameters from animation filenames.
- Treating `m_nodePaths` as the writable parameter list.
- Missing direct Bool condition references.
- Sending ID selectors as integers instead of graph-defined symbols.
- Treating a recognized Vector/Target type code as proof that a safe setter is available.
- Assuming every clip loops because its filename sounds like locomotion.
- Synchronizing damage to animation start when the impact event is later.
- Copying only clips seen during one short test instead of the reachable closure.
- Publishing decompiled game data with documentation instead of keeping a derived contract table.
