# Validation record

Observed on 2026-08-31:

- the project restored against the published `ModSharp.Sharp.Shared 2.1.79`
  package;
- public API usage was cross-checked against the ModSharp interfaces for
  module lifecycle, resource precache, EKV spawn, entity animation, player
  lookup, game-frame hooks, and gamedata registration;
- the source was cross-checked against ModSharp's `IGameData` wrapper and
  native gamedata parser: `Addresses`, `library`, `linux`, `signature`, and
  `factory` are all supported fields;
- ModSharp resolves gamedata signatures with `FindPatternStrict`, which rejects
  both zero matches and multiple matches;
- all four Linux patterns were independently checked against the active
  `libserver.so` and each produced exactly one match;
- each setter's type-specific match is 303 bytes after its function entry, so
  the three `factory: "-303"` transforms resolve the expected entry points;
- the resolver additionally asks ModSharp to confirm that all four resolved
  addresses are distinct function entries before any runtime probe or write;
- the former profile catalogue, Steam build gate, ELF Build ID, module SHA-256,
  embedded JSON loader, and structural classifier were removed;
- no game-tree files, Workshop assets, servers, or running instances were
  modified.

The full compile could not complete in the authoring environment because
MSBuild reported locked intermediate files even with a new isolated artifacts
directory and a serialized, non-reused build node. Run the following in a
clean checkout before publishing:

```bash
dotnet build -c Release
```

Runtime validation still requires a current Linux server build on which all
four signatures resolve uniquely and a complete client/server asset mount. A
successful Windows compile does not exercise native address resolution or
graph materialization.
