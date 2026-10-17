# Layered impact example: provenance and checks

The three `.vpcf` files under `assets/layered-impact/particles/` were authored
on 2026-10-15. They are original small sources, not copied or
decompiled Valve assets. No compiled game content or third-party texture/model
is distributed with them. Asset origin and usage terms remain separate from
native compiler acceptance.

The root starts a large short-lived core and a smaller, faster detail child.
The adjacent `effect-plan.json` records the CP0 placement contract and intended
appearance. Those visual descriptions are authoring goals, not observed parity.

The exact three sources were accepted by the official local CS2 resourcecompiler
on 2026-10-15: three exit codes of zero, three fresh nonempty compiled outputs,
and three successful compiled readbacks with no decoder diagnostics. The root
readback contains both intended child references. The installation reported
Steam build `25640462`, client/server version `2000922`, patch `1.41.8.8` and
SourceRevision `11064488`. Compiler SHA-256:
`00db3daca0e733601bf3fcc1d1bf9df1b2ade805629098c48bd6c51af3d96f51`.

[The portable evidence record](example-native-evidence.json) contains source and
output hashes, compiler arguments, game identity and decoded content from these
original authored sources. It includes no absolute installation path or compiled
binary. Compiled serializers may elide defaults; this record does not assert
complete property retention or prove the meaning of every authored field.

Compilation used fresh scratch addon sources with `-nop4 -fshallow -skiptype
vmat,vmdl,vtex` and the game-specific compiler's `-i`/`-game` inputs. These flags
describe that recorded run, not a universal requirement for other games. To
reproduce, copy the three files under the same addon-relative `particles/` paths
and use the official tools for the recorded target, or the optional standalone
native validation skill. Recompiled binary hashes need not match on another
compiler build. Compare source hashes before reusing this evidence for an edit.

PET appearance and in-game validation were not performed.

The examples deliberately author no explicit material or texture reference.
They may rely on native defaults; that does not prove a polished cyan impact
or verify renderer behavior. Choose actual resources and observe the effect in
PET/CS2 for production use. The simple seed does not restrict the skill's support
for other native classes, providers, renderers, controls or child structures.
