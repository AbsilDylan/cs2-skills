using System;
using System.Collections.Generic;

namespace ModSharpAg2NpcExample.Npc;

internal static class NpcCatalog
{
    internal static readonly NpcPresentationSpec Shambler = new(
        "shambler",
        "Necro Shambler",
        "models/heroes_wip/necro/necro_shambler.vmdl",
        205.0f,
        82.0f,
        "stand_idle",
        "walk_center");

    internal static readonly NpcPresentationSpec AmberTrooper = new(
        "amber",
        "Amber Trooper",
        "models/npc_units/troopers/amber_trooper_01/amber_trooper_01.vmdl",
        170.0f,
        82.0f,
        "idle",
        "run");

    internal static readonly NpcPresentationSpec SapphireTrooper = new(
        "sapphire",
        "Sapphire Trooper",
        "models/npc_units/troopers/sapphire_trooper_01/sapphire_trooper_01.vmdl",
        170.0f,
        82.0f,
        "idle",
        "run");

    internal static IReadOnlyList<NpcPresentationSpec> All { get; } =
    [
        Shambler,
        AmberTrooper,
        SapphireTrooper,
    ];

    internal static bool TryFind(string value, out NpcPresentationSpec spec)
    {
        foreach (var candidate in All)
        {
            if (string.Equals(candidate.Key, value, StringComparison.OrdinalIgnoreCase)
                || string.Equals(candidate.DisplayName, value, StringComparison.OrdinalIgnoreCase))
            {
                spec = candidate;
                return true;
            }
        }

        spec = null!;
        return false;
    }
}
