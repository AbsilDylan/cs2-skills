# Minimal Runtime Blueprint

The bundled [ServerNpcRuntimeSkeleton.cs](../examples/ServerNpcRuntimeSkeleton.cs) is a deliberately incomplete, framework-neutral architecture scaffold, not a drop-in ModSharp module and not a source of signatures or parameter names. It demonstrates boundaries and lifecycle invariants; it does not implement entity spawning, NAV search, Source 2 traces, an owned-effect ledger, or framework registration. Run the dependency-free smoke project under `../tests/ServerNpcRuntimeSkeleton.Tests.csproj` before adapting it; this compiles [ServerNpcRuntimeSkeleton.csproj](../examples/ServerNpcRuntimeSkeleton.csproj) as a project reference.

Adapt it by implementing four narrow game-thread ports:

1. `IBodyPort` resolves full entity identity, moves through collision, and returns typed motor/stop/removal receipts.
2. `ICombatPort` revalidates the target and returns a typed result for one latched damage transaction.
3. `IPresentationPort` projects the snapshot through either a verified named-sequence input or an AG2 adapter and explicitly returns `Applied`, `Retry`, or `Degraded`.
4. `IOwnershipPort` cancels managed work, owns bounded active-world cleanup retries for children/effects/listeners, and forgets state without stale body access after successful body-loss cleanup or world deactivation.

Keep ModSharp wrappers inside those ports. The runtime state and snapshots remain ordinary managed values and can be unit-tested without CS2.

For an AG2 adapter:

- supply parameter names and exact types from a decompiled graph contract;
- acquire the current controller/instance at call time;
- validate entity identity and world generation first;
- use only a current, uniquely resolved typed setter bridge;
- treat Vector/Target as unsupported unless their ABI is independently proven;
- make one-shot pulses edge-triggered by `ActionToken`;
- deduplicate retries by entity identity, presentation revision, and action token;
- report a typed presentation receipt without changing gameplay state.

For a named-sequence adapter, verify that the exact baked sequence label exists
and whether it loops. `AcceptInput` is only the generic entity-I/O dispatcher;
a successful call to a model/entity's verified animation input is evidence for
that named-input path, not evidence that AG2 typed control works.

The skeleton intentionally omits entity creation because spawn and dispatch ownership differ by framework version. Implement creation as a transaction beside the body port, confirm whether the framework helper dispatches automatically, and publish an `NpcIdentity` only after setup succeeds.

Referencing a stock model path on a locally licensed CS2 server for an A/B test
is different from copying its files. Use a native chicken or another CS2-owned
model only as that local positive control. A public sample package should
contain either original/permitted source assets or placeholders plus a
manifest that tells the user where to insert their own model and graph. Never
copy a Deadlock/CS2 extracted monster into this skill repository.

Before calling an adaptation complete, add tests for:

- each legal/illegal action transition;
- impact exactly once, including callback failure;
- stale target and stale entity identity;
- expired/superseded route results;
- death during windup/active/recovery;
- typed stop failure plus bounded cleanup retry/exhaustion;
- presentation failure isolation;
- map-generation cancellation and entity-index reuse.
