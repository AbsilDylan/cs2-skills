namespace ModSharpAg2NpcExample.Npc;

internal sealed record NpcPresentationSpec(
    string Key,
    string DisplayName,
    string Model,
    float MoveSpeed,
    float StopDistance,
    string IdleAnimation,
    string MoveAnimation,
    float ModelScale = 1.0f);
