# Native compilation and delivery

## Contents

- [Identify and isolate the target](#identify-and-isolate-the-target)
- [Build definitions and read back products](#build-definitions-and-read-back-products)
- [Close dependencies before delivering](#close-dependencies-before-delivering)
- [Report the level actually reached](#report-the-level-actually-reached)

## Identify and isolate the target

Resolve the Steam library and app manifest, then verify the selected install's
`steam.inf` when available. Record app/build IDs and compiler/module identity.
App 730 is CS2; the locally inspected Deadlock install uses app 1422450.
The manifests observed in this skill's ledger are examples, not current defaults.

Use an authored addon/content namespace. Work in an existing authorized addon or
a fresh isolated staging addon. Do not replace an installed game's base assets
or change `gameinfo.gi` merely to test a new texture. Resolve content mounts and
packaging behavior from that target's tools/configuration if delivery needs it.

Typical Source 2 trees distinguish sources in `content/<game>_addons/<addon>`
and runtime products in `game/<game>_addons/<addon>`. Check the actual target
layout instead of assuming every game uses the same addon folder name.

## Build definitions and read back products

Run the compiler from its own binary directory with argument-array boundaries,
an explicit source input and explicit game path. A locally verified CS2
invocation shape is:

```powershell
& $compiler -i $sourceDefinition -game $gameDirectory -nop4 -fshallow
```

Here `$compiler` is the resolved `resourcecompiler.exe`, `$gameDirectory` is that
install's `game/csgo`, and `$sourceDefinition` is one authored source definition.
This shape was verified for VPcf on CS2 build 25640462; that number dates
the observation rather than restricting its use. Keep it as a starting
point and inspect the installed help/logs for another game or resource
type, unfamiliar flags, a changed interface or a compile failure. `-fshallow`
is not a dependency-closure guarantee.

Build the texture definition and any required materials before validating the
effect as a whole. MKS and images are source dependencies named by the VTEX;
they are not renamed compiled resources. Record the actual emitted products,
not an assumed output path. Verify a fresh compiled file, inspect native logs,
and decode its metadata and references. Compare nondefault settings with the
source: a successful process can still ignore unsupported keys.

For the helper's `--resource-path materials/owned_test/flipbook.vtex`, copy the
generated `flipbook.vtex`, `flipbook.mks` and frame TGAs into the authorized
addon's content `materials/owned_test/` directory. Compile that `flipbook.vtex`.
After readback, bind the engine resource path `materials/owned_test/flipbook.vtex`
in the renderer shape supported by the target; the runtime loads its compiled
product. The source input path in the VTEX is engine-relative, so compiling a
directory elsewhere without the corresponding content mount is not equivalent.

The October 15 VPcf compiler pass did **not** test production texture/VMAT
closure. A separate [owned texture control](../assets/native-texture-evidence.json)
then compiled the skill's TGA sprite and eight-frame MKS through the supplied
VTEX shape on CS2 build 25640462. The sprite's readback matched every RGBA
component; the sheet retained eight frame display times. This is evidence for
that specific source/format/build, not a new production material or native
effect rendering. Run each new resource's own check separately.

## Close dependencies before delivering

Walk exact references recursively under the selected mount order. Keep these
chains distinct:

```text
Source artwork -> optional MKS -> VTEX source -> VTEX_C + optional sheet metadata
VPcf renderer -> VTEX resource(s) [or a model/material path]
VMAT source -> source images/VTEX -> VMAT_C -> compiled texture references
Model particle -> VMDL_C -> material(s) -> texture(s)
Parent VPcf -> child VPcf -> its own dependencies
```

The native compiler may emit companion/generated files. Inventory them rather
than predicting names. For each dependency, record path, source mount, size,
hash and status: authored and included, provided by the target base game, or
missing. Two same-named files from different mounts are not automatically the
same resource. Preserve engine-relative paths and avoid absolute machine paths
inside deliverables.

Compiled sheet data can be embedded in the VTEX. Do not demand that `.mks` must
ship as a runtime file when the compiler embedded it, or omit it from the source
delivery needed for editing. A source package and a runtime package answer
different needs.

Inspect the final VPK/package's entries and references after packaging. Loading
from loose files in Tools does not alone prove a recipient can load a Workshop
package. Verify in the intended consumer with the required base-game mount and
without accidental access to a development extraction directory.

## Report the level actually reached

- **Source checked:** images/alpha/order and source declarations inspected.
- **Compiled/read back:** named target compiler emitted resources; decoded
  settings and dependencies agree with the intended nondefault controls.
- **Previewed independently:** useful visual check in a stated tool, with its
  supported subset and approximations.
- **Rendered natively:** observed in the named target build, scene and times.

Keep each level separate. Native compilation is valuable even when no graphical
tools are available; deliver that result and the remaining native-render check
without manufacturing screenshots or parity claims.
