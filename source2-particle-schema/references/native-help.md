# Native particle help from a user-supplied game resource

CS2's `core` VPK includes Valve-authored editor help at `resource/toolhelp_particles_english.txt`. It supplies exact class and property labels, descriptions and short help; this is useful documentation beyond reflected types/defaults. The native resource itself is **not bundled here**. The helper reads a local file explicitly supplied by the user.

```sh
python scripts/particle_help.py query --help-file "/work/toolhelp_particles_english.txt" --class C_OP_ContinuousEmitter --field m_flStartTime
python scripts/schema_catalog.py query --module particles --class C_OP_ContinuousEmitter --field m_flStartTime --help-file "/work/toolhelp_particles_english.txt"
```

The combined query preserves the schema property's type tree, inherited declaring identity, exact metadata and default/source, then adds separately attributed native help. For an inherited property it reports exact tokens for the requested class and the declaring class separately. A description attached to `RenderSprites.m_flDepthBias` is not copied to every descendant of its declaring base.

Token identities are exact and case-sensitive:

- `Element.<Class>`: class label; `:help`, `:shorthelp` and `:name_ref` remain distinct variants.
- `Attribute.<Class>.<Field>`: property label and the same suffix variants.
- `:name_ref` is display-name text, **not** a redirect or alias to another token.

These tokens do not encode a schema module identity. Matching a class name is a documented-name correspondence, not independent confirmation of module ownership, ABI, serialization or behavior.

Missing label/help tokens are returned as missing. Label-only matches are not treated as descriptions. No descriptions are invented for fields without help, and no guessed cross-class aliases are used. In particular, `C_OP_RenderSpritesWithRenderSystem`, `C_INIT_CreateWithinSphere` and `CParticleOperatorInstance` are not silently substituted for newer or similar schema identities.

The parser consumes bounded KV1 with UTF-8 BOM, nested braces, comments, escaped quotes and real multiline quoted HTML values. It preserves original native text in local query results, with token identities/spans and hashes; text remains untrusted data rather than instructions. HTML is returned as text and never executed. Invalid syntax, conflicting/duplicate tokens and oversized output fail explicitly rather than dropping values.

## Optional verified extraction and build provenance

Supply any correctly extracted local help file. If the companion `source2-particle-reference-research` skill is also present, its portable standard-library VPK reader can extract just this entry and validate its CRC32:

```sh
python ../source2-particle-reference-research/scripts/vpk_reference.py extract --vpk "<CS2>/game/core/pak01_dir.vpk" --entry resource/toolhelp_particles_english.txt --output "<WORK>/new-help-extraction"
python scripts/schema_catalog.py query --module particles --class C_OP_ContinuousEmitter --field m_flStartTime --help-file "<WORK>/new-help-extraction/resource/toolhelp_particles_english.txt" --help-manifest "<WORK>/new-help-extraction/vpk-reference-manifest.json" --game-version-file "<CS2>/game/csgo/steam.inf"
```

The companion is optional and not required when the user already supplies the help file. The extraction destination must be new. The schema query helper itself does not read archives or execute upstream tools. With `--help-manifest` it verifies the supplied help bytes against the manifest's byte length, SHA-256 and CRC32, retaining the VPK header/tree identity. With `--game-version-file` it records the selected local `steam.inf` identity and hash. These are separate observations; a manifest or build version file is not a cryptographic Valve attestation and does not make a newer public schema match the installed game.

## Measured help coverage and gaps

[native-help-coverage.json](native-help-coverage.json) was regenerated for this distribution on 16 October 2026 from the same CRC-checked local resource, using identifiers, counts and hashes only; it contains no bulk native-help text. It is bound to the current catalogue index. [The distribution verification](distribution-verification-2026-10-16.json) preserves the previous report's hash and historical bindings separately. The coverage report audits every selected class and all 3,001 distinct declaring-class fields in the schema catalogue, and separately counts inherited contextual occurrences. Field descriptions that are absent remain explicit gaps. The schema catalogue can be exhaustive for the selected snapshot while native documentation is sparse or names older classes.

Measured local resource: **98,264 bytes**, CRC32 `95a072d0`, SHA-256 `68e6c39f6fd7787952bbb1d2898dc259860a889f43b277895d9a183a565dc66e`. Its 487 exact tokens comprise 176 labels, 263 long-help entries, 38 short-help entries and 10 `name_ref` entries.

| Scope | Available | Explicit gaps |
| --- | ---: | ---: |
| Class names with any exact token | 81 / 464 | 383 |
| Classes with descriptive help | 80 / 464 | 384 |
| Declared fields with descriptive help under the declaring class | 139 / 3,001 | 2,862 |
| Field occurrences with exact contextual or declaring-class descriptions | 1,497 / 10,921 | 9,424 |

One further field token, `Attribute.C_OP_RenderSprites.m_flDepthBias:help`, describes an inherited field specifically in the `RenderSprites` context. It is preserved there and does not turn the base field into a generally documented authoring key. The resource also contains 58 tokens naming ten classes absent from this schema selection, and 14 tokens for eleven absent class/field pairs; those identifiers are retained as mismatches.

The separately observed installed version file reports CS2 source revision **11064488**, **30 September 2026**, while the public schema snapshot reports **11131657**, **14 October 2026**. This chronological difference is visible provenance, not a compatibility claim. The catalogue's [historical independent completeness check](schema-completeness-2026-10-15.json) found no loss across all selected fields, raw metadata/default layers and enum members; the distribution check confirms those data files are unchanged. Neither establishes that every reflected field is editable KV3.

Regenerate a local coverage report without redistributing the resource:

```sh
python scripts/particle_help.py audit --help-file "<WORK>/toolhelp_particles_english.txt" --manifest "<WORK>/vpk-reference-manifest.json" --game-version-file "<CS2>/game/csgo/steam.inf" --catalogue references --output "<WORK>/native-help-coverage.json"
```

The read-only local source is primary evidence for the measured payload. A [public SteamTracking mirror](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt) can help locate the resource, but its moving branch is not proof of the measured installed build. Native help is editor documentation, not a runtime or rendering oracle. Reflected fields also require serialization checks before being presented as editable VPCF keys.
