# Original AnimGraph2 Source Authoring

Use this reference when the task requires a new graph topology or private
control parameters rather than only replacing clips in an existing graph. The
supported architecture is deliberately source-first:

```text
original project IR
  -> deterministic text KV3 CNmGraphDocument (.vnmgraph)
  -> Valve ResourceCompiler from the installed, profiled CS2 build
  -> compiled CNmGraphDefinition (.vnmgraph_c)
  -> independent inspection and normalized semantic comparison
  -> isolated runtime canary
```

Do not implement a production writer for `.vnmgraph_c`. The private compiler
lowers document UUIDs, pins, connections, state-local ordinals, resource slots,
node indexes, variations, `RERL`, `RED2`, and Binary KV3 `DATA`. Reproducing
only the outer container can create a parsable but invalid or crashing graph.

## Contents

- [Current Evidence And Its Boundary](#current-evidence-and-its-boundary)
- [Source Document Contract](#source-document-contract)
- [Deterministic IR And UUIDs](#deterministic-ir-and-uuids)
- [Controls And Runtime Ownership](#controls-and-runtime-ownership)
- [Topology Promotion Ladder](#topology-promotion-ladder)
- [Toolchain And Compiler Profile](#toolchain-and-compiler-profile)
- [Validation Gates](#validation-gates)
- [Redistribution Boundary](#redistribution-boundary)

## Current Evidence And Its Boundary

A documented research run on 2026-08-31 proved original source authoring on
Steam build `25000182` (`PatchVersion 1.41.7.8`). This is a historical proof
receipt, not permission to reuse the profile after a game update.

```text
resourcecompiler.exe SHA-256
  0F72EBD0E86676EA809451D9B0E26F63D149FB7C3F698CF328F8D260CB7B3C90
resourcecompiler.dll SHA-256
  7F36431861B944256A433CE56FD3FE0B11C51D8AA7399C1FD007A69F5D8BB6CF
installed assettypes_common.txt preimage SHA-256
  D8C1CE4F6AB014D7BEF8BA9C134A9FABB2AFE5CF3CFAF9FEE84C05C89BC38E44
isolated overlay assettypes_common.txt SHA-256
  42CAA5A1851BBFA3F16944A7E23AA7BCF6242EAF6EB66BF23C91017114871717
overlay registrations
  vnmgraph -> CompileNmGraph
  vnmskel  -> CompileNmSkeleton
  vnmclip  -> CompileNmClip
CompileNmGraph fingerprint in the new output
  27
Source2Viewer-CLI used for independent inspection
  19.1.6199+c350f81b77be944acf928998cea96e12b24837ef
Source2Viewer-CLI SHA-256
  14176B31E49CCD10A147AB5B2F90E053E443A4714CCD3228B746EB70E71136E5
```

The public tool registry in that build contained no `vnmgraph`, `vnmskel`, or
`vnmclip` compiler registrations, although `resourcecompiler.dll` contained
`CompileNmGraph`, `CompileNmSkeleton`, and `CompileNmClip`. No supported public
standalone AG2 editor was found. Private ModelDoc/editor strings and cheat
debug commands prove internal infrastructure, not a supported public UI.

The proof used a copied, isolated toolchain and a copied registry augmented
only with those three mappings. It made no change to the Steam installation.
In that overlay:

- the exact original L0 in
  [minimal-l0.vnmgraph](../examples/minimal-l0.vnmgraph) compiled without a
  correction;
- ResourceCompiler reported `1 compiled, 0 failed`;
- source SHA-256 was
  `C5957979E93D4E70ACD30B02F88A13DE0E3ACAF66A9FD0D803C48A2E7A1802DB`;
- output was 1,787 bytes with SHA-256
  `76556F332DE56A32D9EB7472BEFB8544E9F16734F1644536E7D7F71989994638`;
- Source2Viewer parsed header version 12 and `RERL`, `RED2`, and `DATA` blocks;
- `DATA` contained one `CNmClipNode::CDefinition`, root index `0`, the expected
  clip slot, looping flag, and disabled root motion;
- the included neutral fixture compiled twice to the same output hash.

The equivalent isolated invocation shape is:

```powershell
$probeRoot = 'C:\path\to\isolated-ag2-probe'
& (Join-Path $probeRoot 'game\bin\win64\resourcecompiler.exe') `
  -game (Join-Path $probeRoot 'isolated\game\csgo') `
  -fshallow `
  -i (Join-Path $probeRoot 'isolated\content\csgo_addons\ag2_probe\animation\examples\minimal-l0.vnmgraph')
```

The machine-specific root is deliberately omitted. The hashes and relative
overlay layout above are the reproducible parts of the receipt.

The receipt used the pinned VRF 19.1 CLI above, not the newer local GUI or the
latest upstream release. Reinspect with a pinned current VRF build as an
additional result; do not silently replace the historical oracle in the
receipt.

The receipt fixture references a placeholder clip path under a neutral example
namespace and the installed Valve viewmodel skeleton path; it redistributes
neither dependency. Copy it into a private namespace and replace both paths
with compatible, authorized project resources. For NPC use, first provide an
NPC-compatible skeleton and clip. Its recorded hash and compile result no
longer apply after any replacement.

Use only the evidence labels defined in `SKILL.md`. L0 is `source-authored`,
`compiled`, and `inspected` on the recorded profile. A normalized VRF semantic
comparison is supporting inspection evidence, not a new label. The receipt is
not a general claim that arbitrary nodes or topologies work.

## Source Document Contract

A source graph is generic text KV3 with this envelope:

```text
_class = "CNmGraphDocument"
m_nVersion = 0
m_pRootGraph = CNmGraphDocFlowGraph
m_variationHierarchy
m_debugParameterSets = []
m_dictionaryIDSetIDs = []
```

Every graph, node, pin, and connection has a unique UUID. A flow-graph edge
resolves four UUIDs in the same graph: source node, source output pin,
destination node, and destination input pin. Pin names, types, direction, and
order are class schema, not free-form labels.

The minimal BlendTree is:

```text
CNmGraphDocument v0
├─ variation Default -> one skeleton
└─ root CNmGraphDocFlowGraph / BlendTree
   ├─ CNmGraphDocClipNode
   │  ├─ Play In Reverse : Bool input
   │  ├─ Reset Time      : Bool input
   │  └─ Pose            : Pose output
   ├─ CNmGraphDocPoseResultNode
   │  └─ Out             : Pose input
   └─ Clip.Pose -> PoseResult.Out
```

The PoseResult pin named `Out` is an input. A minimal variation is `Default`,
has no parent, names the exact `.vnmskel`, and has null user data. For a
server-translated NPC idle, start with looping enabled and sampled root motion
disabled. Enable root motion only after ownership and movement semantics are
proved in a canary.

Classify fields before minimizing:

- editor-only/defaultable: comments, node positions, graph view offset/zoom,
  previews, and debug parameter sets;
- authoring structure: class names, UUIDs, fixed pins, connections, child and
  secondary graph shape, state mappings, and resolved references;
- runtime semantics: control names and types, skeleton and variations, clips,
  looping/root motion/events, state conditions, transitions, and referenced
  graph resources.

Removing tested presentation fields changed only the source fingerprint in a
current-build output. That does not prove that arbitrary empty arrays or
unknown metadata can be removed. Preserve fields until a controlled ablation
test proves them defaultable for the exact profile.

Do not use a decompiled runtime-shaped object such as a tiny graph beginning
with `m_nRootNodeIdx` as an authoring template. A source must be a real
`CNmGraphDocument`; feeding a compiled-definition-shaped KV3 to the current
Nm graph compiler caused an access violation in the probe environment.

## Deterministic IR And UUIDs

Generate documents from an original, versioned IR. Do not build graph source
with global string replacement over a stock or decompiled Valve graph.

```text
DocumentSpec
  irVersion
  projectNamespaceUuid
  documentKey
  variations[]
  controls[]
  root: GraphSpec

GraphSpec
  stableKey
  kind
  nodes[]
  connections[]       # absent for StateMachineGraph

NodeSpec
  stableKey
  kind                 # closed allowlist
  semanticProperties
  childGraph?
  secondaryGraph?
```

Generate UUIDv5 values from semantic paths:

```text
document namespace = UUIDv5(project namespace, "ag2-doc/" + documentKey)
graph ID = UUIDv5(document namespace, "graph/" + graphPath)
node ID  = UUIDv5(document namespace, "node/" + nodePath)
pin ID   = UUIDv5(document namespace, "pin/" + nodePath + "/" + direction + "/" + pinKey)
edge ID  = UUIDv5(document namespace, "edge/" + sourcePath + "->" + targetPath)
```

Stable keys are separate from display names and array positions. Fixed pins
come from a build-profiled class registry; callers cannot rename, reorder, or
retype them. Serialize variations parent-first, controls in declared order,
functional nodes before the terminal Result, pins in schema order, and edges
in one canonical order. Emit invariant-culture finite numbers. Two generations
from the same IR must be byte-identical.

## Controls And Runtime Ownership

The source schema supports root control nodes for Bool, Float, ID, Vector, and
Target. Each has no input and one fan-out-capable `Value` output of the exact
type. A reference in a child graph must carry the root control UUID, exact
value type, exact name, and group. Never leave a resolved parameter reference
at type `Unknown`.

Authorability is not runtime writability:

| Control | Source graph | Profiled server-owned NPC bridge |
|---|---|---|
| Bool | static-observed | setter exercised by a profiled runtime bridge on an exact build |
| Float | static-observed | setter exercised by a profiled runtime bridge on an exact build |
| ID | static-observed | setter exercised by a profiled runtime bridge on an exact build |
| Vector | schema and compiled fixture observed | current Linux ABI only; canary required |
| Target | schema/source fixture observed | current Linux ABI only; strict canary required |
| BoneMask | graph-internal value type | no entity setter evidence; do not expose |

Route controller materialization, native signatures, parameter lookup, setter
ABI, and replication questions to `$cs2-ag2-npc-runtime`. `AcceptInput` does
not create an AnimGraph2 controller or arbitrary missing controls. Legacy
`SetAnimation` addresses published sequence behavior, not private AG2 values.

A server setter also does not create a generic channel into client-owned
graphs. First-person weapon arms are evaluated on a client-local HUD-model
entity. Weapon and player/agent private roots can use custom clips and graph
topology, but normally must consume the native client parameter contract unless
a separate client bridge exists.

Practical boundary:

- server-owned NPC model entity: strongest target for a greenfield graph and
  private Bool/Float/ID controls;
- weapon 1P/3P: custom roots and clips are feasible, arbitrary new server-driven
  inputs are constrained by client ownership and prediction;
- player/agent root: feasible only while preserving native variations,
  locomotion, IK, events, and skeleton contracts; start by extending a proven
  compatible family, not with an empty greenfield root.

## Topology Promotion Ladder

Promote one semantic feature at a time.

### L0: one looping clip

Use the included Clip-to-PoseResult document. Prove compilation, independent
inspection, model linkage, idle playback, a remote observer, reconnect, and map
change before adding controls.

### L1A: one custom Float blend

Add one root Float control, two Clip nodes, and one
`CNmGraphDocBlend1DNode`. Its Parameter input is Float, dynamic pose pins map
one-to-one to blend points by pin UUID, and its Pose output feeds PoseResult.
This topology is the preferred first proof that an original private variable
affects a server-owned NPC. It remains only `static-observed` until the actual
document earns `source-authored` or `generated`, `compiled`, and `inspected`;
claim `route-proven` and `third-person-validated` only after their named runtime
evidence exists.

### L1B: Idle/Action state machine

Only after L1A, add a Bool request control and two states. A StateMachineGraph
links states and conduits by UUID and does not have flow connections. Each state
owns a child BlendTree ending in PoseResult and the required secondary
ValueTree/state-layer data. The entry condition pin mapping must have the same
cardinality and order as its target-state UUID mapping. Local conduits resolve
both start and end state UUIDs.

Keep state-dependent conditions such as StateCompleted and TimeRemaining out
of global conduits. A previous graph compiled with such a condition but crashed
at runtime because there was no current state context. Compilation is not a
memory-safety proof.

Referenced graphs are usable only after skeleton and parameter compatibility
checks. External graph/pose slots remain experimental until an original source
fixture compiles, decompiles to the expected slot ID, and passes runtime tests.

## Toolchain And Compiler Profile

Before every authoring run, record:

```text
Steam build ID and patch version
resourcecompiler.exe and resourcecompiler.dll hashes
assettypes_common.txt hash and Nm registration state
source KV3 encoding/format versions
CompileNmGraph RED2 fingerprint
VRF release, commit, executable/package hash
```

Fail closed on an unknown profile. Compiler fingerprints 26 and 27 have both
been observed in local resources; artifacts and golden files cannot be
promoted between them merely because both parse.

If the installed registry reports no Nm compiler, prefer a copied, isolated
toolchain for research. Never silently modify the installed Steam registry,
never copy an old complete registry over a new build, and never redistribute
Valve executables, DLLs, or a modified registry. Any direct installed-toolchain
repair requires explicit user approval, an exact preimage hash, a narrow diff,
a backup, and a restoration receipt; see
[authoring-and-compilation.md](authoring-and-compilation.md).

Compile in dependency order:

```text
VNM skeleton
-> source animation/DMX and VNM clips
-> referenced child graphs
-> parent/root graph
-> models
-> package closure
```

## Validation Gates

Reject before ResourceCompiler when any gate fails:

1. All source inputs and fixtures are original or redistribution-authorized.
2. Project paths are game-relative, private, normalized, and contain no `_c`
   suffix or `..` segment.
3. Stable keys and every generated UUID are unique.
4. `Default` has one valid skeleton; variation parents form an acyclic tree.
5. Every edge endpoint is local and resolved; pin types match exactly; fan-out
   rules hold; every BlendTree has exactly one reachable PoseResult terminal.
6. Every parameter/state/resource reference resolves with the expected class
   and type; entry-pin/state mappings have equal cardinality.
7. No state-context condition is emitted in a global conduit.
8. A second generation is byte-identical and an independent KV3 parser accepts
   the source.

After compilation:

1. Require an expected output for every input and preserve full diagnostics.
2. Parse the `_c` independently; verify header and `RERL`/`RED2`/`DATA`.
3. Check root/node/resource bounds, control IDs and types, clip data slots,
   referenced/external slots, and state-local ordinals.
4. Decompile with a pinned VRF build and compare normalized semantics while
   ignoring regenerated UUIDs and editor layout. An unsupported node makes the
   result inconclusive, not successful.
5. Inspect the Workshop closure and downloaded VPK.
6. Run a disposable runtime canary with action sentinels, negative controls,
   owner and remote observer clients, cancellation, reconnect, and map change.

VRF is a decompiler/schema oracle, not the Source 2 evaluator. Its viewer plays
selected clips but does not execute state machines, IK, or constraints, and its
generic resource serializer is not production-ready. A VRF parse or semantic
round-trip therefore never replaces the runtime canary.

## Redistribution Boundary

Public artifacts may contain an original IR, generator, validators, and wholly
original minimal fixtures. Do not ship:

- Valve graph sources or decompiled Valve graphs;
- Valve models, skeletons, clips, compiler binaries, DLLs, or registry files;
- VRF `Tests/Files` fixtures or other assets with unclear game provenance;
- templates derived by copying and editing a stock graph.

Discover ResourceCompiler in the user's local installation. If code or binaries
from ValveResourceFormat are distributed or adapted, preserve its MIT license
and third-party notices. When VRF materially powers the workflow, include the
project-requested attribution: `Powered by Source 2 Viewer
(ValveResourceFormat)`.
