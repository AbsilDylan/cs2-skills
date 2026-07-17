# Before you do your things

Some stuff may be wrong, i just know it worked for me :
- models ported from CS:GO/sketchfab (animated models) to CS2
- custom AG2 animations for 1st & 3rd persons
- using NPCs with AG2 animations

So enjoy if it works for you !

# CS2 Agent Skills

AI-agent skill packages for current Counter-Strike 2 community-server asset
research and authoring.

This is an unofficial community project. It is not affiliated with or endorsed
by Valve. The repository contains original documentation and source tooling,
not extracted game resources. Do not commit or redistribute Valve-extracted
resources, compiled game assets, or third-party work without permission.

## Skills

| Skill | Scope |
|---|---|
| `cs2-ag2-npc-runtime` | Existing model-entity NPC runtimes: compiled graph inspection, controller materialization, typed parameters, behavior projection, Linux signature recovery, and NPC Workshop closure |
| `cs2-animgraph2-authoring` | Weapon/item presentation: VNMClip/VNMGraph authoring, private first/third-person roots, proxy routing, prediction, and item Workshop delivery |
| `cs2-player-model-porting` | Player-character assets: skeleton retargeting, skinning, geometry, materials, ModelDoc, first-person body geometry, hitboxes, ragdolls, and player-model Workshop closure |

Use `cs2-ag2-npc-runtime` for model entities such as `prop_dynamic_override`
that need server-driven NPC behavior. Use `cs2-animgraph2-authoring` for weapon
or item first/third-person graph roots. Use `cs2-player-model-porting` for the
geometry, rig, and physics of a player character.

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
never part of the repository or compiled handoff. The example's artifact
policy is deliberately `blocked`: compilation can be tested locally, but an
artifact handoff is allowed only after a concrete redistribution basis covers
every generated and transitive input and a separate basis covers preserved
VNMClip template fields.

See the skill's
[`portable-tooling.md`](cs2-animgraph2-authoring/references/portable-tooling.md)
for commands and the example manifest.

## Installation Notice

Until an explicit repository license is added, the installation commands are
operational examples for the owner and explicitly authorized evaluators; they
do not grant permission to copy or redistribute the repository.

## Install With Codex

Ask Codex to install a GitHub skill path with `$skill-installer`:

```text
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
| NPC Linux typed bridge | Historical exact build/hash profile in [`linux-parameter-bridge.md`](cs2-ag2-npc-runtime/references/linux-parameter-bridge.md); no bundled runtime receipt | Bool/Float/ID require local reproduction; Vector/Target are diagnostic-only and not writable |
| AnimGraph2 clip tooling | Blender 4.1.1 and the dated CS2 tools profile in [`portable-tooling.md`](cs2-animgraph2-authoring/references/portable-tooling.md) | Windows CS2 toolchain; other Blender/tool versions unverified |
| Player-model porting | Contract-driven guidance without a bundled dated runtime receipt | Must derive and record a current official target before each port |

Do not label an output `current`, `packaged`, or `runtime-proven` unless its
machine-readable report records the exact inputs, tools, artifact hashes, and
validation layer.

## Licensing

No repository license has been selected yet. Do not assume permission to copy,
modify, or redistribute this repository until the owner adds an explicit
license. Each input processed by a skill also retains its own provenance and
license requirements.
