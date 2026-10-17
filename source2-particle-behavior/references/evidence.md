# Native evidence and verification

## Evidence levels

| Level | Establishes | Does not establish |
|---|---|---|
| **Typed** | Class/field identity, declared type, enum values, reflected metadata and build-scoped default source | Complete runtime meaning or every combination of fields |
| **Documented** | Valve-authored explanation of intended behavior and units in the identified help resource | Exact formula, all edge cases or equivalence across game/build variants |
| **Serialized** | Controlled native compiler acceptance/preservation or default stripping | Simulated values, lifecycle, dependency closure or pixels |
| **Measured** | Recorded native runtime result for identified inputs/build/environment | Untested branches, other builds or every renderer/material |
| **Unknown** | A particular behavior has not been established by available evidence | That the field is invalid, useless, or should be discarded |

A resource viewer's implementation and API documentation are primary evidence of that project's reconstruction. They can suggest experiments, but are not a native engine oracle. A field label is not a complete description, and a constructor/default object is not a measured trajectory.

## Embedded compiler observations

[native-compiler-evidence.json](native-compiler-evidence.json) is a portable record of thirteen controlled compilations/readbacks:

- CS2 Steam build `25640462`, patch `1.41.8.8`, SourceRevision `11064488`, version date 30 September 2026.
- Compiler SHA256 `00db3daca0e733601bf3fcc1d1bf9df1b2ade805629098c48bd6c51af3d96f51`.
- All thirteen compilations and readbacks succeeded; no native game runtime or pixels were observed.
- Each fixture retains input/output hashes, diagnostics and actual decoded native KV3. `authoredTestIntent` is a descriptive test record, not a native format.
- The portable derivation records its source evidence hash. Unknown-sentinel names are omitted while their locations/values, absence after compilation and original hashes remain explicit.

Useful controlled findings: constant radius 5 was omitted while 7 survived; Simple FadeOut time 0.25 was omitted while 0.37 survived; particular CP selections, sphere minimum-radius providers, orientation tokens, gravity/drag and other nondefault inputs survived readback. Unknown sentinel fields were silently dropped despite exit zero. These are **Serialized**, not **Measured** behavior claims.

The schema snapshot may identify a different revision. Keep its default/type evidence separate from the compiler's installed build. A native asset can contain a field not present in a newer snapshot, and a reflected field may not be exercised by a particular compiled example.

## Primary help and reconstruction sources

[native-help-facts.json](native-help-facts.json) embeds 22 concise factual interpretations from a locally extracted Valve help asset: 98,264 bytes, CRC32 `95a072d0`, SHA256 `68e6c39f6fd7787952bbb1d2898dc259860a889f43b277895d9a183a565dc66e`. Length/hash/CRC were checked against the VPK extraction manifest. Exact help keys, source-text hashes and line spans are retained without redistributing the complete asset. The contemporaneous version-file observation identifies revision 11064488, but does not cryptographically bind that version to the VPK. These are **Documented** facts, not measured native behavior.

Valve distributes `resource/toolhelp_particles_english.txt` with explanatory class/field text. Prefer the target installation's copy, recording VPK/entry identity and CRC/hash. The [SteamTracking mirror](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt) exposes Valve-authored text, but a moving mirror is not automatically the same build as the installed compiler.

Help keys distinguish `Element.<class>`, `Attribute.<class>.<field>`, `:help` and `:shorthelp`. Old renderer aliases such as `WithRenderSystem` are not automatically exact aliases of every current class. Query exact class/field/inherited owner and record whether a match is exact, inherited, aliased or absent.

The schema skill (`$source2-particle-schema`) supplies typed lookup and optional target-help querying. Do not redistribute the complete help asset or invent descriptions for fields without help. These guides use concise authored explanations and preserve uncertainty around formulas.

[VRF](https://github.com/ValveResourceFormat/ValveResourceFormat) and [its schema explorer](https://s2v.app/SchemaExplorer/cs2/particles) are useful primary reconstruction/type sources. A link to an independent implementation must not be relabelled “Valve implementation”.

## Native verification method

Start with a material/renderer and emitter known to work in the target tools. Save a diagnostic copy of the effect and pin build, resource/dependency identities, random controls, CP setup, timestep, camera/exposure, component order and lifecycle. Change one property while retaining an active control.

For a new field or representation:

1. Compile omitted, explicit-default and nondefault variants to fresh outputs.
2. Read back the intended field and its type. Distinguish default omission from silent discard.
3. Run the native effect and inspect the relevant attribute, count or pixels.
4. Probe a boundary and an alternative representation.
5. Restart and test an independent instance before generalizing reproducibility.
6. Add the intended composition, changing only one dependency at a time.

Use observations that discriminate possible implementations. Examples:

- A nonzero CP0 and distinct CP1 expose incorrect anchoring; translating the full setup tests the intended coordinate contract.
- One and several particles reveal collection/cursor mistakes; a particle born between updates exposes time-accounting assumptions.
- Lifetimes other than one second distinguish normalized lifetime from seconds.
- Min/default/max inputs and values outside the range reveal clamp/extrapolation behavior.
- Multiple particles, ticks, children, restarts and changed seeds distinguish RNG stability from unintended correlation.
- Zero, half and full alpha/size plus overlapping geometry distinguish visibility, color, blending and depth.

A picture alone may hide a wrong attribute or an overridden input. Conversely, a correct scalar trace does not establish a shader/material result. Record both when needed. Skipped, unavailable or unrun tests remain unverified.

Use [composition cases](composition-cases.md) as concrete starting points. Report exact observed results, not just “looks correct”, and retain **Unknown** for unmeasured native behavior.
