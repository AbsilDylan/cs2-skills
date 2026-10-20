# Observed production patterns

## Contents

- [Moving projectile and zero-speed facing](#moving-projectile-and-zero-speed-facing)
- [A trail leaves old particles behind](#a-trail-leaves-old-particles-behind)
- [Short events and their visible tail](#short-events-and-their-visible-tail)
- [Parameter defaults belong to the effect](#parameter-defaults-belong-to-the-effect)
- [Case provenance](#case-provenance)

Use these notes for moving projectiles, trails, attached indicators and short
events. They summarize specific CS2 Particle Editor cases recorded on
16–17 October 2026. The original captures and complete production assets are
not bundled with this skill. These are bounded case notes, not a claim that
every field or newly authored effect has been runtime-tested.

## Moving projectile and zero-speed facing

For a gameplay projectile, define who owns travel, collision and hit timing.
An effect can follow a CP supplied by a server/plugin while its own particles
provide the model, animation and wake. A PET helper moving that CP is a test
driver; it does not implement the game's projectile or hand attachment.

The observed model case used a zero-radius CP0 spawn and this operator pair:

```text
{
    _class = "C_OP_PositionLock"
    m_TransformInput = {
        m_nType = "PT_TYPE_CONTROL_POINT"
        m_nControlPoint = 0
        m_bUseOrientation = false
    }
    m_bLockRot = false
}
{
    _class = "C_OP_RemapCPVelocityToVector"
    m_nControlPoint = 0
    m_nFieldOutput = 21
    m_flScale = 1
    m_bNormalize = true
}
```

In this CS2 case, attribute 21 supplied the particle normal. The model had its
long axis authored along Z; `C_OP_RenderModels` used `m_bIgnoreNormal=false`
and `m_bOrientZ=true`. Native PET observation showed the model facing along a
moving +Y trajectory. During a stationary delay it stood vertically: the
velocity operator overwrote the initialized normal `[1,0,0]`. This combination
did **not** preserve the last heading at zero speed.

If a charge-up or stopped pose must remain aimed, provide an explicit heading
contract and verify it at zero speed, or separate the held and flying phases.
Do not claim that a one-time normal initializer defeats a later update writer.
Check first movement, stopping and restarting using an asymmetric model.

The observed hero was a one-particle burst with a 1.85-second lifetime, alongside
continuous wake children. That source contract supports a finite flight; it does
not promise unlimited travel. Match all layer lifetimes and cleanup to the
caller's intended flight window.

For hand launch, the caller resolves the actual hand attachment at launch and
then drives projectile position. A preview figure only establishes approximate
visual scale. For a fixed arrival time, the caller's trajectory must implement
that time contract and define moving-target and obstruction behavior. Setting
particle lifespan alone cannot make a gameplay projectile arrive or register a hit.

## A trail leaves old particles behind

The observed trail suite used moving CP0 input and retained visible wake behind
the moving origin. One electric recipe continuously emitted points at CP0 and
connected them with `C_OP_RenderRopes` in creation order; its old path points had
no position-lock operator. This is a useful starting pattern for a history of
emitter positions. A speed-stretched `C_OP_RenderTrails` sprite serves a different
geometry contract; choose by the desired result.

For a combined projectile, the hero and wake need different following rules:
keep the hero attached to the moving CP, and let previous wake particles follow
their authored world motion. Moving every old wake point with the owner can
drag the whole trail forward.

Test the final CP-driven effect while translating and turning its source. At
zero speed, a time-based emitter can continue placing particles near the same
point; decide whether that accumulation is acceptable. Native observations of
these moving helpers established a visible trail. Their interrupted PET stop
checks did not establish server stop propagation or an exact natural tail.

## Short events and their visible tail

For “at most one second,” budget the longest layer. With ordinary finite
emission and lifespan decay, a useful authored bound is:

```text
layer end ≈ child activation delay + emitter start
            + emission window + maximum particle lifetime
effect end ≈ latest layer end
```

For an uncapped burst emitted in one update, use a zero emission window as the
planning approximation. An instantaneous emitter's per-frame cap can distribute
births across updates; verify that schedule and lifetime treatment separately.
This bound is not a universal engine equation: delayed endcaps, loops, pre-age,
lifetime writers or other triggers need their own schedule. Check all reachable
children; a short root lifespan does not shorten independent child emission.

Valve's Simple fade help uses fractions of particle lifespan. A fade duration
of `0.25` means a quarter of that life, so it spans 0.2 seconds for a 0.8-second
particle. It does not mean 0.25 seconds. Ranged fade proportional settings have
their own contract; see [motion and lifetime](motion-lifetime.md#alpha-fades-and-death).

Model animation, particle lifespan and PET simulation speed are separate.
A five-second clip or lifespan readback proves authored timing, while a
half-speed preview cannot provide a five-second wall-clock measurement.
Shorten or retime the relevant clip and particles together when the brief
requires a faster motion; verify the apparent movement as well as disappearance.

Two recorded finite mesh compositions had authored tails of 0.86 and
0.93 seconds. Final normal-speed, 30 fps one-shot recordings each showed a
visible viewport window of approximately 0.867 seconds, conservatively bounded
by 0.90 seconds, followed by at least one second of empty output. The first
included a finite preview actor, so this bound is not an isolated measurement
of runtime-only particle death. A looped art capture was used only for appearance.

Use `source2-particle-validation` when available for a timing capture. Establish
the final source revision, normal playback and natural completion; a forced
editor stop or an edited demonstration video cannot establish the requested tail.

## Parameter defaults belong to the effect

Two exercised designs deliberately used different scalar interfaces:

| Design | Authored input contract | Consequence |
|---|---|---|
| Size percentage | CP.X × 0.01; caller initializes 100 | Zero produces zero scale. A PET saved value does not initialize the game caller. |
| Optional size bonus | CP.X remapped from 0..100 to a positive base..double scale | Zero retains the base size; 100 requests double scale. |

These are authored mappings, not engine-wide CP defaults. A successful CP0
motion test also does not verify a separate size parameter. Give the caller
the actual defaults and choose probes from this effect's contract.

Likewise, an optical intensity input can hide a refractive layer while its
emitter remains active. One floor-wake case visibly disappeared and returned
under Y=100→0→100. That proves the observed optical response; it does not
establish emission shutdown, destruction or resource cleanup.

## Case provenance

These SHA-256 fingerprints identify the original observation records reviewed
for this summary. They are provenance, not expected hashes for a recipient's
new work, and the source records/captures are not prerequisites for authoring.

| Recorded case | Observation-record SHA-256 |
|---|---|
| Moving model projectile and attached indicator, 16 October 2026 | `efe52ce3c148861d8258a7fa3cba9c09ba74898fdba26195045964e9ef3829ef` |
| Five moving trails and a finite jump rune, 16 October 2026 | `265925d727571caf8ef0ad9385367f0b8b83198026db21b3ce89cb67e5d65a57` |
| Two short mesh events and a refractive floor wake, 17 October 2026 | `530ba7602e834818b7bf67607cc9ae87160d98ea0cc4a0c611a9f378fd7f8849` |

The projectile operator fragment came from source SHA-256
`992a59df02e03f065453bb88fcdb00a7e465b09792284854f6e10b779d5f15a9`.
Game collision, custom hand attachment, server replication, real-map rendering
and concurrency were not established by these PET observations.
