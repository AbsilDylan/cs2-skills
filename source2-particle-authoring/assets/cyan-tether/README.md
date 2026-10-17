# Cyan tether: prompt-to-source integration example

Original source artwork and VPCF for the creative brief below. No Valve asset is
included.

> CS2: a cyan ring around CP0, a luminous line to CP1, a few fragments
> attracted to the target, and a soft disappearance over a total two seconds.

Root: `source/particles/skill_eval/cyan_tether/root.vpcf`. The source tree
contains four VPCF, three RGBA TGA and three VTEX definitions. Preserve its
addon-relative `particles/` and `materials/` paths when staging in a new addon.
Compile the three VTEX, then the four VPCF, with the target CS2 tools.
No separate VMAT is authored by this direct-texture graph.

The caller supplies CP0 (world origin) and CP1 (world target) before emission.
Baseline: CP0=(0,0,8), CP1=(160,0,24), identity orientations. No internal writer
claims these CPs. The ring initializes at CP0; the path and attraction consume
CP1. The detailed contract and proposed moving/rotated/replay scenarios are in
[the plan](effect-plan.json). CP propagation and live motion still need native
observation with the actual spawning driver.

These exact original source files were compiled on CS2
build 25640462 / SourceRevision 11064488: seven zero exit codes and seven fresh
outputs, with no source repairs. Four particle readbacks decoded successfully.
The three texture readbacks are RGBA8888 and match the owned TGA pixels.
[The evidence](native-evidence.json) records source hashes, output hashes,
retained fields and omissions without compiled binaries or absolute user paths.

This proves the tested source pipeline and selected serialization. It does not
prove the ring plane, rope topology, endpoint inclusion, native force equation,
CP motion, two-second fade, visibility, occlusion or pixels. Those are authored
intentions awaiting PET/in-game observation. Unknown fields may be stripped;
absent defaults and unsupported fields must not be conflated.
