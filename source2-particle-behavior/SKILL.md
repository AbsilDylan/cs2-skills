---
name: source2-particle-behavior
description: "Design and diagnose native Source 2 particle emission, providers, motion, lifetime, CPs and rendering, using typed contracts and documented or measured evidence."
---

# Native Source 2 particle behavior

Translate visual intent into properties with explicit units, data sources, coordinate spaces and lifecycle. Use the schema skill (`$source2-particle-schema`) for exact class/field identities, inherited contracts, enums and build-scoped defaults. A friendly label is not a complete behavior description.

Read only the families needed:

- [Observed production patterns](references/observed-patterns.md): moving projectiles, world-space trails, zero-speed facing, short events and CP defaults learned from native PET cases.
- [Providers](references/providers.md): literal/random/attribute/CP sources, maps, curves, interpolation and evaluation context.
- [Initializers](references/initializers.md): point, shell, box, local velocity, offsets and captured scalar/vector state.
- [Emission and time](references/emission-time.md): bursts, streams, delays, duration, capacity, stop conditions and restart.
- [Motion and lifetime](references/motion-lifetime.md): gravity, drag, forces, size, fades, decay and their composition.
- [Control points and children](references/control-points-children.md): data versus transforms, spaces, attachment and inheritance.
- [Rendering](references/rendering.md): sprite/model/trail/rope choices, orientation, alpha, sequences and materials.
- [Composition cases](references/composition-cases.md): concrete native experiments with expected observations and unresolved boundaries.

Use four evidence levels: **Typed** (schema identity/type/metadata), **Documented** (Valve-authored help), **Serialized** (controlled native compile/readback), and **Measured** (identified native runtime observation). Mark formulas or timing **Unknown** when those sources do not establish them. An independent resource viewer's implementation can suggest a probe; it is not a Valve runtime oracle.

Do not remove valid native fields because an independent renderer cannot implement them. Preserve exact native tokens. Read inherited operator timing/strength/end-cap controls before attributing an unexpected result to the principal field alone.

Compile and read back the values relevant to the change: native compilation may discard unknown fields or omit default-valued fields. Use omitted/default/nondefault controls when an omission is ambiguous. [Embedded evidence](references/native-compiler-evidence.json) contains thirteen controlled CS2 compiler/readback observations. [Native help facts](references/native-help-facts.json) carry 22 concise interpretations with exact tokens, passage hashes and verified source-payload identity; [evidence and verification](references/evidence.md) records the scope. Read the relevant fixture or fact rather than loading both complete JSON records.

For a reproducible behavior check, pin game/build, resource/dependency identities, CP bindings, initial attributes, random controls, timestep, component order, camera/material and lifecycle events. Test an isolated property with an active control, then expand to a composition. Report the behavior established and its environment rather than certifying all fields because a file compiled.

Build identities date observations; they do not restrict the skill to those builds. Reuse established patterns and investigate the affected contract when a change or regression warrants it.
