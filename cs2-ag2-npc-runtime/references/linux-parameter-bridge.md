# Linux AG2 Typed Parameter Bridge

## Contents

- [When To Use This Bridge](#when-to-use-this-bridge)
- [Call Contract](#call-contract)
- [Keep The Runtime Profile Local](#keep-the-runtime-profile-local)
- [Store Signatures As Build Data](#store-signatures-as-build-data)
- [Resolve And Classify Safely](#resolve-and-classify-safely)
- [Recover Signatures After A CS2 Update](#recover-signatures-after-a-cs2-update)
- [Validate At Runtime](#validate-at-runtime)
- [Failure Policy](#failure-policy)

## When To Use This Bridge

Use a native bridge only when the server framework has no verified public API for setting AG2 control parameters. The bridge should call existing engine functions; it should not patch code, alter `libserver.so`, or write guessed graph/controller fields.

Keep the bridge narrow:

```text
parameter name -> global engine symbol
entity + parameter symbol -> runtime parameter type
Bool/Float/ID value -> matching engine setter
```

Everything else remains normal managed plugin logic.

The documented bridge is deliberately partial: it recognizes the graph's Bool,
ID, Float, Vector, and Target type codes. A historical external investigation
reported Bool, ID, and Float setters, but this repository does not bundle the
raw runtime receipt needed to call them proven. Vector and Target remain
unsupported until their payload ABI, lifetime rules, and setters are
independently recovered for the exact build.

Resolve against the loaded Linux module at startup. Treat signatures and structural markers as build-scoped data in configuration, not constants scattered through code.

## Call Contract

The historically reported unmanaged shapes are equivalent to:

```csharp
delegate* unmanaged<nint, nint, byte> getParameterType;
delegate* unmanaged<nint, nint, nint, int, void> setParameter;
```

Conceptual arguments:

```text
getParameterType(entityPointer, addressOfParameterSymbol)
setParameter(entityPointer, addressOfParameterSymbol, addressOfTypedValue, 0)
```

Observed type codes in the historical profile:

```text
1 -> Bool
2 -> ID
3 -> Float
4 -> Vector (getter/diagnostic only)
5 -> Target (getter/diagnostic only)
```

Convert both parameter names and ID values through the same engine global-symbol/string-token facility expected by these functions. Do not pass a managed string pointer, hash guessed from another subsystem, or enum ordinal.

Before every getter or setter call:

1. Marshal execution onto the server game thread.
2. Validate entity index plus generation/serial, lifetime, and native pointer at call time.
3. Revalidate the controller/graph instance used by the call.
4. Resolve the parameter-name symbol.
5. Ask the engine for the runtime parameter type.
6. Compare that type with the intended setter and reject Vector/Target writes in this bridge.
7. Pass a correctly sized local typed value by address.

Do not assume a managed exception can recover from a bad native dereference; an access violation can terminate the process before managed recovery runs.

## Keep The Runtime Profile Local

This public skill deliberately contains no callable byte pattern, RVA, copied
ELF, or claim that a historical setter still matches the current game. Put the
recovered profile under an ignored local evidence directory and promote only
its schema and recovery method to a public repository.

A complete local profile records every part of the call contract, not only the
scanner patterns:

```text
observed date and operator/tool versions
platform and Steam build ID
ELF Build ID and module SHA-256
getter and setter-candidate patterns
structural classification markers
expected raw and classified match counts
calling convention and exact getter/setter prototype shapes
runtime type-code mapping
parameter-symbol conversion, size, and alignment
Bool/Float/ID payload size and alignment
resolved module-relative addresses for diagnosis only
graph/model hashes used by the positive control
runtime probe results and receipt hash
```

Never call an RVA directly. ASLR changes absolute addresses, game updates move
functions, and a matching prologue does not prove semantics. Recover patterns
from the exact target binary using the procedure below.

## Store Signatures As Build Data

Prefer a versioned JSON/TOML configuration loaded at startup. A useful schema is:

```json
{
  "platform": "linux-x64",
  "observedDate": "<UTC date>",
  "steamBuildId": "<exact build>",
  "elfBuildId": "<exact ELF build ID>",
  "moduleSha256": "<exact SHA-256>",
  "typeGetterPattern": "<locally recovered pattern>",
  "setterCandidatePattern": "<locally recovered pattern>",
  "candidateWindowBytes": 384,
  "expectedMatches": {
    "getterRaw": 1,
    "setterCandidatesRaw": "<exact count>",
    "boolClassified": 1,
    "idClassified": 1,
    "floatClassified": 1
  },
  "abi": {
    "callingConvention": "<exact current module ABI>",
    "getterPrototype": "<verified shape>",
    "setterPrototype": "<verified shape>",
    "parameterSymbol": {
      "conversion": "<verified engine facility>",
      "size": "<bytes>",
      "alignment": "<bytes>"
    },
    "payloads": {
      "bool": { "size": "<bytes>", "alignment": "<bytes>" },
      "float": { "size": "<bytes>", "alignment": "<bytes>" },
      "id": { "size": "<bytes>", "alignment": "<bytes>" }
    }
  },
  "typeCodes": { "bool": 1, "id": 2, "float": 3, "vector": 4, "target": 5 },
  "writeSupport": [ "bool", "id", "float" ],
  "runtimeReceiptSha256": "<receipt hash>"
}
```

Keep this populated file local unless its binary provenance can legally and
reproducibly accompany the evidence. Add comments in the implementation that
point to this recovery procedure. Keep only recovery and validation logic in
public code. Calling convention, prototypes, type codes, symbol conversion,
and payload width/alignment are exact-module evidence and must match the local
profile plus runtime receipt before any call is enabled.

## Resolve And Classify Safely

Use the framework's module scanner, such as a `FindPatternMulti` equivalent, rather than hand-walking executable memory.

At startup:

1. Identify the loaded `libserver.so` module and executable ranges.
2. Scan the getter pattern and require exactly one structurally valid match.
3. Scan the shared setter pattern and collect all matches.
4. Inspect only a bounded byte window inside each candidate's executable mapping.
5. Classify candidates by the type compare and typed store markers.
6. Require exactly one Bool, one Float, and one ID setter.
7. Confirm all resolved addresses lie inside the expected module executable range.
8. Log module identity, relative addresses, candidate counts, and classification.
9. Mark the candidate set structurally resolved only when every invariant
   succeeds, but keep all writes disabled. Activate writes only after the exact
   binary passes the isolated runtime validation below and its receipt is
   recorded.

Perform resolution at startup, but invoke resolved entity/graph functions only on the server game thread. A worker may analyze immutable copied bytes offline; it must not retain or dereference live entity/controller pointers.

Do not select candidates by scan order alone. Function layout can reorder between builds.

Wildcard only unstable data such as branch displacements. Keep invariant opcodes, member-displacement bytes, virtual call shape, type comparison, and typed store as verification anchors. A pattern made mostly of wildcards is not update-resilient; it is ambiguity hidden as flexibility.

## Recover Signatures After A CS2 Update

Perform recovery offline against a copied binary from the exact target server build. Do not reverse engineer or probe the live production process.

### 1. Record binary identity

```bash
readelf -n libserver.so
sha256sum libserver.so
```

Record the Steam app build ID and CS2 patch beside the ELF Build ID and hash.

### 2. Find semantic string anchors

Search for animation-parameter diagnostics:

```bash
strings -tx libserver.so | grep -Ei \
  'Failed to set animgraph param|Unable to find.*graph parameter|Setting an animgraph parameter via Pulse'
```

Wording changes are possible. Also search shorter fragments such as `animgraph param`, `graph parameter`, and `Pulse`.

### 3. Follow xrefs and direct calls

Open the ELF in Ghidra/IDA/Binary Ninja, or use `objdump` around candidate xrefs. Find wrappers that:

- accept a model entity and parameter symbol;
- obtain the body/animation controller through a virtual call;
- obtain the graph instance/controller data;
- test a parameter type;
- write a typed value through a small direct callee.

The semantic string usually identifies a higher-level wrapper. Follow its direct calls to the small getter/setter functions rather than signing the large wrapper.

### 4. Classify functions by behavior

Confirm the getter returns a small type code. Confirm setters compare that code and store the intended width:

- Bool: one-byte store;
- Float: scalar single-precision store;
- ID: pointer/token-sized store.

Reject candidates that merely share a prologue.

### 5. Build new patterns

Choose a window containing:

- the function prologue;
- verified controller/graph acquisition structure;
- type compare and/or typed store;
- no absolute address or relocation bytes;
- wildcards for relative branch/call displacements.

Test uniqueness on the exact binary and at least one nearby archived build when available.

### 6. Update evidence and comments

Store the new patterns, build IDs, hash, observed RVAs, marker changes, analysis tool, and validation result. Preserve old build records for diagnosis; do not silently overwrite their provenance.

## Validate At Runtime

Use one known-good AG2 NPC and one invalid parameter on an isolated non-player staging server:

1. Ensure a watchdog and an independently reachable out-of-process restart path are active.
2. Resolve functions at startup with writes disabled.
3. Ask the getter for graph-proven Bool, Float, ID, Vector, and Target parameters from the game thread.
4. Confirm returned types match the static graph contract; mark Vector/Target as diagnostic-only.
5. Enable Bool/Float/ID writes for the positive control only.
6. Set one harmless continuous Float and observe the expected animation change.
7. Pulse one Bool exactly once.
8. Set one valid ID symbol.
9. Query a nonexistent parameter and require a clean failure.
10. Despawn/reuse an entity index and prove a stale generation/serial is rejected before a native call.
11. Verify a remote client sees the result.
12. Record the exact module identity, graph contract, resolved relative
    addresses, typed probe results, observer result, and receipt hash. Only that
    matching binary profile may subsequently enable production writes.

Log counters such as attempted writes, accepted type matches, missing parameters, type mismatches, and disabled-bridge calls. Do not log every successful write indefinitely.

## Failure Policy

Fail closed when:

- the module identity is unknown after an update;
- a pattern has zero or multiple unclassified matches;
- typed setters cannot be classified uniquely;
- an address lies outside the module executable range;
- the getter disagrees with the decompiled graph contract;
- the known-good runtime probe fails.
- execution is not on the server game thread;
- entity generation/serial, controller, or graph-instance lifetime cannot be proven;
- a caller requests Vector or Target through this partial bridge.

Keep gameplay running with static or legacy animation fallback when possible. Print one actionable startup error containing the build identity and missing resolver stage. Never fall back to old RVAs or direct memory writes.

Keep native writes disabled by default on production until the exact binary identity has passed staging. Rate-limit bridge failures, expose a health status, and let the watchdog restart the process after a native crash; do not treat `try/catch` as a crash boundary.
