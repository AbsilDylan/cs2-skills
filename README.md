# Before you do your things

Some stuff may be wrong, i just know it worked for me :
- models ported from CS:GO/sketchfab (animated models) to CS2
- custom AG2 animations for 1st & 3rd persons
- using NPCs with AG2 animations

So enjoy if it works for you !

# CS2 Agent Skills

AI-agent skill packages for current Counter-Strike 2 community-server runtime,
asset research, and authoring.

This is an unofficial community project. It is not affiliated with or endorsed
by Valve. The repository contains original documentation and source tooling,
not extracted game resources. Do not commit or redistribute Valve-extracted
resources, compiled game assets, or third-party work without permission.

## Skills

| Skill | Scope |
|---|---|
| `cs2-server-npc-runtime` | Server-authoritative NPC gameplay with or without AG2: identity, lifecycle, AI, navigation, collision movement, combat, cleanup, scheduling, hot reload, and validation |
| `cs2-ag2-npc-runtime` | Existing AG2 NPC presentation: compiled graph inspection, controller materialization, typed parameters, fallback classification, Linux signature recovery, and Workshop closure |
| `cs2-animgraph2-authoring` | Weapon/item presentation: VNMClip/VNMGraph authoring, private first/third-person roots, proxy routing, prediction, and item Workshop delivery |
| `cs2-player-model-porting` | Player-character assets: skeleton retargeting, skinning, geometry, materials, ModelDoc, first-person body geometry, hitboxes, ragdolls, and player-model Workshop closure |

Use `cs2-server-npc-runtime` for NPC gameplay and lifecycle independently of
its animation backend. Add `cs2-ag2-npc-runtime` when an existing model entity
such as `prop_dynamic_override` needs AG2 materialization or typed animation
control. Use `cs2-animgraph2-authoring` for weapon or item first/third-person
graph roots, and `cs2-player-model-porting` for player geometry, rigs, and
physics.

## Bundled NPC Runtime Blueprint

`cs2-server-npc-runtime/examples/ServerNpcRuntimeSkeleton.cs` is a compilable,
framework-neutral, asset-free C# design scaffold—not an operational ModSharp
plugin. It demonstrates full
entity identity, bounded state transitions, impact latching, fail-isolated
ports, active cleanup, world-forget semantics, and a presentation snapshot. It
contains no ModSharp API guesses, model paths, signatures, or game assets.

The companion references explain how to adapt the ports to the exact framework
version and hand only the presentation snapshot to an AG2 or verified
named-sequence adapter. No example bundles native CS2/Deadlock assets. A
path-only native control still requires the user to supply a lawful complete
resource closure and does not grant redistribution rights.

## Bundled ModSharp AG2 Example

[`cs2-ag2-npc-runtime/examples/modsharp-ag2-npc-example`](cs2-ag2-npc-runtime/examples/modsharp-ag2-npc-example/)
is the concrete framework example for spawning an AG2 model entity, registering
Linux signatures through ModSharp gamedata, probing Bool/Float/ID parameter
types, and applying typed values on the game thread.

Use that project when the target framework is ModSharp instead of generating a
framework-neutral approximation of its EKV, spawn, hook, gamedata, or entity
APIs. Other frameworks should adapt the documented engine ABI and safety
contract to their own public interfaces rather than copying ModSharp types.

The example contains no compiled game resources. Its native model paths are
local positive controls only. The example module source is separately
MIT-licensed, as permitted by ModSharp's third-party module exception;
ModSharp itself retains its own license.

## Bundled AnimGraph2 Tooling

`cs2-ag2-npc-runtime/scripts/summarize_vnmgraph.py` turns a locally decompiled
VNMGraph into a parameter/clip contract report. It ships no game data.

`cs2-animgraph2-authoring/scripts/` includes a manifest-driven clip pipeline
validated against the recorded reference baseline. Other current weapons or
items require fresh reference inspection and are not assumed compatible:

```text
VPK discovery/extraction -> exact Blender 1P/3P rigs -> complete DMX export
-> current-template VNMClip generation -> ordered ResourceCompiler build
```

The example uses Five-SeveN references only to demonstrate the schema and is a
clip-tool smoke test, not a complete item diagnostic suite. Paths, skeletons,
translation contracts, actions, output namespaces, and compile order are all
manifest data. Local Valve-derived references stay under `.local/` and are
never part of the repository or compiled handoff. Since 2026-09-03 the
exporter converts clips to the compiler frame (raw VRF 19.1 references
otherwise render off-screen) and can carry a weapon skeleton's joints as the
clip's secondary animation (`secondary_skeleton_dmx`). The example's artifact
policy is deliberately `blocked`: compilation can be tested locally, but an
artifact handoff is allowed only after a concrete redistribution basis covers
every generated and transitive input and a separate basis covers preserved
VNMClip template fields.

See the skill's
[`portable-tooling.md`](cs2-animgraph2-authoring/references/portable-tooling.md)
for commands and the example manifest.

## Installation Notice

This repository is distributed under the Apache License 2.0. Installation does
not change the provenance or licensing requirements of third-party inputs or
locally extracted Valve-derived references, which are not relicensed by this
repository.

## Install With Codex

Ask Codex to install a GitHub skill path with `$skill-installer`:

```text
$skill-installer install https://github.com/AbsilDylan/cs2-skills/tree/main/cs2-server-npc-runtime
$skill-installer install https://github.com/AbsilDylan/cs2-skills/tree/main/cs2-ag2-npc-runtime
$skill-installer install https://github.com/AbsilDylan/cs2-skills/tree/main/cs2-animgraph2-authoring
$skill-installer install https://github.com/AbsilDylan/cs2-skills/tree/main/cs2-player-model-porting
```

Install every folder when a workflow can span player assets, item graphs, and
NPC runtime control. Individual installations do not resolve cross-skill
handoffs automatically.

Manual installation also works: copy each skill directory into
`$CODEX_HOME/skills` (or `~/.codex/skills` when `CODEX_HOME` is unset). The
`agents/openai.yaml` files provide optional Codex interface metadata;
`SKILL.md` remains the portable runtime contract.

## Install With Claude Code

Install the repository as a Claude Code marketplace:

```text
/plugin marketplace add AbsilDylan/cs2-skills
/plugin install cs2-skills@absildylan-cs2-skills
```

Claude Code namespaces plugin skills. They can be invoked explicitly as:

```text
/cs2-skills:cs2-server-npc-runtime
/cs2-skills:cs2-ag2-npc-runtime
/cs2-skills:cs2-animgraph2-authoring
/cs2-skills:cs2-player-model-porting
```

Alternatively, copy individual skill folders into `.claude/skills/` for one
project or `~/.claude/skills/` for one user. Claude.ai accepts one skill folder
per ZIP; the Claude API accepts a ZIP or individual files through its Skills
API. These surfaces do not synchronize skills with each other, and neither
requires a `claude.yaml` file.

## Validate

Run the dependency-free repository validator before publishing:

```text
python -B tools/validate_skills.py
python -B -m unittest discover -s tools/tests -v
python -B -m unittest discover -s cs2-ag2-npc-runtime/tests -v
python -B -m unittest discover -s cs2-animgraph2-authoring/tests -v
python -B tools/validate_skills.py
dotnet run --project cs2-server-npc-runtime/tests/ServerNpcRuntimeSkeleton.Tests.csproj -c Release --artifacts-path <temporary-directory-outside-this-repository> --disable-build-servers
npx --yes --package=@anthropic-ai/claude-code@2.1.197 -- claude plugin validate . --strict
```

It validates portable frontmatter, descriptions, direct reference links,
OpenAI metadata, Claude marketplace paths, repository safety, and the schema of
the routing fixtures under `evals/`. Those fixtures do not themselves invoke a
model; use them as a forward-evaluation corpus. The final command runs Claude
Code's official marketplace validator at the version pinned by CI.

## Compatibility Evidence

All native offsets, signatures, graph layouts, tool behavior, and stock assets
are build-scoped evidence rather than permanent APIs.

| Area | Recorded evidence | Portability status |
|---|---|---|
| Server NPC navigation/runtime | Managed architecture, framework-neutral scaffold, and offline NAV-artifact contract; no current native `CNavMesh` ABI, signature profile, or runtime receipt is bundled | Prefer offline NAV artifacts; any native NAV read bridge requires exact binary provenance, bounded reads, isolated canary validation, and fail-closed behavior |
| NPC Linux typed bridge | ModSharp gamedata example plus recovery procedure in [`linux-parameter-bridge.md`](cs2-ag2-npc-runtime/references/linux-parameter-bridge.md); signatures were observed on 2026-08-31 and no raw RVA is used | Revalidate strict uniqueness, factory distances, function entries, and live Bool/Float/ID probes after every CS2 update; Vector/Target remain unsupported |
| AnimGraph2 clip tooling | Blender 4.1.1 and the dated CS2 tools profile in [`portable-tooling.md`](cs2-animgraph2-authoring/references/portable-tooling.md) | Windows CS2 toolchain; other Blender/tool versions unverified |
| Clip DMX frame | Compiler frame rule (root-level bones permuted and rotated versus raw VRF 19.1 axes) observed in game on build 2000899, 2026-09-03; exporter converts by default (`reference_dmx_frame`) | Proven for first-person clips with a static root bone; third-person locomotion untested |
| Secondary weapon animation | Stock clips carry `m_secondaryAnimations` for the weapon skeleton; a custom weapon skeleton compiled with 56 + 28 tracks (build 2000899, 2026-09-03) | Compile-proven; custom-skeleton in-game playback still pending |
| Weapon identity | `weapon_type` = VData `m_szAnimClass` else `m_szName` (shared graph controller code, build 2000899) | Subclass resolution on a clean client still to be observed |
| Player-model porting | Contract-driven guidance without a bundled dated runtime receipt | Must derive and record a current official target before each port |

Do not label an output `current`, `packaged`, or `runtime-proven` unless its
machine-readable report records the exact inputs, tools, artifact hashes, and
validation layer.

## Licensing

Unless otherwise noted, the repository-authored content is licensed under the
[Apache License 2.0](LICENSE). This grant applies only to material the copyright
holder is entitled to license. Every third-party input processed or referenced
by a skill retains its own provenance, copyright, and redistribution terms.
