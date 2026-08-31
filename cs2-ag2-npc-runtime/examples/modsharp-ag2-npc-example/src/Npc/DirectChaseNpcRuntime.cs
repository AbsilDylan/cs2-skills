using System;
using System.Collections.Generic;
using System.Linq;
using ModSharpAg2NpcExample.Animation;
using Sharp.Shared;
using Sharp.Shared.Enums;
using Sharp.Shared.GameEntities;
using Sharp.Shared.Managers;
using Sharp.Shared.Types;

namespace ModSharpAg2NpcExample.Npc;

/// <summary>
/// Intentionally simple movement example: each NPC is teleported in a flat,
/// straight line toward the nearest living player. It does not query NAV,
/// traces, gravity or collision and therefore does not avoid walls or levels.
/// </summary>
internal sealed class DirectChaseNpcRuntime
{
    private const string EntityClassname = "prop_dynamic_override";
    private const int MaximumActiveNpcs = 24;
    private const double UpdateIntervalSeconds = 0.05;
    private const double MaterializationRetrySeconds = 0.05;
    private const double MaterializationTimeoutSeconds = 2.0;

    private readonly IModSharp _modSharp;
    private readonly IEntityManager _entities;
    private readonly Ag2ParameterWriter _writer;
    private readonly List<TrackedNpc> _npcs = [];
    private readonly List<IPlayerPawn> _targets = [];
    private double _nextUpdateAt;
    private int _nextNpcId = 1;

    internal DirectChaseNpcRuntime(
        IModSharp modSharp,
        IEntityManager entities,
        Ag2ParameterWriter writer)
    {
        _modSharp = modSharp;
        _entities = entities;
        _writer = writer;
    }

    internal int ActiveCount => _npcs.Count;
    internal bool CanSpawn => _writer.IsResolved;
    internal string NativeStatus => _writer.Describe();

    internal (int Spawned, string Status) SpawnAround(
        IPlayerPawn requester,
        NpcPresentationSpec spec,
        int requestedCount)
    {
        if (!_writer.IsResolved)
        {
            return (0, _writer.Describe());
        }

        var available = MaximumActiveNpcs - _npcs.Count;
        var count = Math.Clamp(requestedCount, 1, Math.Min(8, Math.Max(1, available)));
        if (available <= 0)
        {
            return (0, $"limit reached ({MaximumActiveNpcs})");
        }

        var spawned = 0;
        var eyeAngles = requester.GetEyeAngles();
        var requesterOrigin = requester.GetAbsOrigin();
        for (var index = 0; index < count && _npcs.Count < MaximumActiveNpcs; index++)
        {
            var yaw = eyeAngles.Y + (index * (360.0f / count));
            var radians = yaw * (MathF.PI / 180.0f);
            var offset = new Vector(MathF.Cos(radians), MathF.Sin(radians), 0.0f) * 180.0f;
            var origin = requesterOrigin + offset + new Vector(0.0f, 0.0f, 8.0f);
            var facing = new Vector(0.0f, NormalizeYaw(yaw + 180.0f), 0.0f);
            if (TrySpawn(spec, origin, facing))
            {
                spawned++;
            }
        }

        return (spawned, $"spawned {spawned}/{count} {spec.DisplayName}");
    }

    internal void Update(bool simulating)
    {
        if (!simulating || _npcs.Count == 0)
        {
            return;
        }

        var now = _modSharp.EngineTime();
        if (now < _nextUpdateAt)
        {
            return;
        }

        _nextUpdateAt = now + UpdateIntervalSeconds;
        BuildTargets();
        for (var index = _npcs.Count - 1; index >= 0; index--)
        {
            var npc = _npcs[index];
            if (!IsAvailable(npc.Entity))
            {
                _npcs.RemoveAt(index);
                continue;
            }

            ScheduleThink(npc.Entity);
            if (!npc.ControllerReady)
            {
                if (!TryMaterialize(npc, now))
                {
                    if (now >= npc.MaterializationDeadline)
                    {
                        _modSharp.LogWarning(
                            $"[AG2 NPC Example] Removing #{npc.Id}: AG2 controller timeout ({npc.LastAg2Status}).");
                        Destroy(npc.Entity);
                        _npcs.RemoveAt(index);
                    }

                    continue;
                }
            }

            UpdateChase(npc, now);
        }
    }

    internal void Clear(bool destroyEntities)
    {
        if (destroyEntities)
        {
            foreach (var npc in _npcs)
            {
                Destroy(npc.Entity);
            }
        }

        _npcs.Clear();
        _targets.Clear();
        _nextUpdateAt = 0.0;
    }

    private bool TrySpawn(
        NpcPresentationSpec spec,
        Vector origin,
        Vector angles)
    {
        var id = _nextNpcId++;
        var keyValues = new Dictionary<string, KeyValuesVariantValueItem>
        {
            ["targetname"] = $"ag2_npc_example_{id}",
            ["origin"] = origin.ToString(),
            ["angles"] = angles.ToString(),
            ["model"] = spec.Model,
            ["use_animgraph"] = 1,
            ["animateonserver"] = 1,
            ["randomizecycle"] = 0,
            ["solid"] = 0,
        };

        try
        {
            // SpawnEntitySync performs create + precache + DispatchSpawn.
            // Calling DispatchSpawn a second time here would be a bug.
            var entity = _entities.SpawnEntitySync<IBaseAnimGraph>(
                EntityClassname,
                keyValues);
            if (entity is null || !entity.IsValid())
            {
                return false;
            }

            entity.SetName($"ag2_npc_example_{id}");
            entity.SetModelScale(spec.ModelScale);
            entity.AnimGraphUpdateEnabled = true;
            entity.SetMoveType(MoveType.None);
            entity.SetGravityScale(0.0f);
            entity.SetCollisionGroup(CollisionGroupType.Npc);
            entity.SetSolid(SolidType.None);
            entity.Teleport(origin, angles, new Vector());
            entity.SetAbsVelocity(new Vector());
            entity.SetLocalVelocity(new Vector());
            ScheduleThink(entity);
            _ = entity.AcceptInput("TurnOn", entity, entity);
            _ = entity.AcceptInput("Enable", entity, entity);

            var now = _modSharp.EngineTime();
            _npcs.Add(new TrackedNpc(
                id,
                spec,
                entity,
                now,
                now + MaterializationTimeoutSeconds));
            return true;
        }
        catch (Exception exception)
        {
            _modSharp.LogWarning(
                $"[AG2 NPC Example] Spawn #{id} failed: {exception.GetType().Name}.");
            return false;
        }
    }

    private bool TryMaterialize(TrackedNpc npc, double now)
    {
        if (now < npc.NextMaterializationAttempt)
        {
            return false;
        }

        npc.NextMaterializationAttempt = now + MaterializationRetrySeconds;
        npc.LastAg2Status = "controller-not-ready";
        if (!_writer.TryActivate(npc.Entity, out var activationStatus))
        {
            npc.LastAg2Status = activationStatus;
            return false;
        }

        var baseline = new[]
        {
            Ag2Parameter.Bool("in_air", false),
            Ag2Parameter.Float("time_scale", 1.0f),
            Ag2Parameter.Float("forward_speed", 0.0f),
            Ag2Parameter.Float("move_speed", 0.0f),
            Ag2Parameter.Float("look_heading", 0.0f),
            Ag2Parameter.Id("base_action", "none"),
        };
        if (!TryApply(npc, baseline, out var baselineStatus))
        {
            npc.LastAg2Status = baselineStatus;
            return false;
        }

        npc.ControllerReady = true;
        npc.LastAg2Status = "controller-ready";
        SetNamedAnimationHint(npc.Entity, npc.Spec.IdleAnimation);
        _modSharp.LogMessage(
            $"[AG2 NPC Example] #{npc.Id} {npc.Spec.DisplayName}: typed AG2 controller ready.");
        return true;
    }

    private void UpdateChase(TrackedNpc npc, double now)
    {
        var origin = npc.Entity.GetAbsOrigin();
        if (!TryFindNearestTarget(origin, out var targetPosition, out var distance))
        {
            SetMovingState(npc, moving: false);
            npc.LastUpdateAt = now;
            return;
        }

        if (distance <= npc.Spec.StopDistance)
        {
            SetMovingState(npc, moving: false);
            npc.Entity.SetAbsVelocity(new Vector());
            npc.Entity.SetLocalVelocity(new Vector());
            npc.LastUpdateAt = now;
            return;
        }

        var direction = new Vector(
            targetPosition.X - origin.X,
            targetPosition.Y - origin.Y,
            0.0f);
        var horizontalLength = direction.Length2D();
        if (horizontalLength <= 0.001f)
        {
            SetMovingState(npc, moving: false);
            npc.LastUpdateAt = now;
            return;
        }

        direction /= horizontalLength;
        var delta = Math.Clamp(now - npc.LastUpdateAt, 0.0, 0.1);
        var travel = MathF.Min(
            npc.Spec.MoveSpeed * (float)delta,
            MathF.Max(0.0f, distance - npc.Spec.StopDistance));
        var next = origin + (direction * travel);
        var yaw = MathF.Atan2(direction.Y, direction.X) * (180.0f / MathF.PI);
        var velocity = direction * npc.Spec.MoveSpeed;

        if (!SetMovingState(npc, moving: true))
        {
            return;
        }

        npc.Entity.Teleport(next, new Vector(0.0f, yaw, 0.0f), velocity);
        npc.Entity.SetAbsVelocity(velocity);
        npc.Entity.SetLocalVelocity(velocity);
        npc.LastUpdateAt = now;
    }

    private bool SetMovingState(TrackedNpc npc, bool moving)
    {
        var speed = moving ? npc.Spec.MoveSpeed : 0.0f;
        var parameters = new[]
        {
            Ag2Parameter.Bool("in_air", false),
            Ag2Parameter.Float("forward_speed", speed),
            Ag2Parameter.Float("move_speed", speed),
            Ag2Parameter.Float("look_heading", 0.0f),
            Ag2Parameter.Float("time_scale", 1.0f),
        };
        if (!TryApply(npc, parameters, out var status))
        {
            if (npc.LastAg2Status != status)
            {
                _modSharp.LogWarning(
                    $"[AG2 NPC Example] #{npc.Id} AG2 write failed: {status}.");
            }

            npc.LastAg2Status = status;
            return false;
        }

        npc.LastAg2Status = "locomotion-applied";
        if (npc.IsMoving != moving)
        {
            npc.IsMoving = moving;
            SetNamedAnimationHint(
                npc.Entity,
                moving ? npc.Spec.MoveAnimation : npc.Spec.IdleAnimation);
        }

        return true;
    }

    private bool TryApply(
        TrackedNpc npc,
        IEnumerable<Ag2Parameter> parameters,
        out string status)
    {
        foreach (var parameter in parameters)
        {
            var result = _writer.Apply(npc.Entity, parameter);
            if (!result.Applied)
            {
                status = result.Status;
                return false;
            }
        }

        status = "applied";
        return true;
    }

    private static void SetNamedAnimationHint(
        IBaseAnimGraph entity,
        string animation)
    {
        // Parameters remain authoritative. This one-shot hint only unsticks
        // graphs whose protected spawn clip has latched on the client.
        _ = entity.AcceptInput("SetDefaultAnimation", entity, entity, animation);
        _ = entity.AcceptInput("SetAnimation", entity, entity, animation);
        _ = entity.AcceptInput("SetPlaybackRate", entity, entity, 1.0f);
    }

    private void BuildTargets()
    {
        _targets.Clear();
        foreach (var controller in _entities.GetPlayerControllers(true))
        {
            try
            {
                var pawn = controller.GetPlayerPawn();
                if (pawn is not null && pawn.IsValid() && pawn.IsAlive)
                {
                    _targets.Add(pawn);
                }
            }
            catch
            {
                // A controller can disappear while the entity list is read.
            }
        }
    }

    private bool TryFindNearestTarget(
        Vector origin,
        out Vector targetPosition,
        out float distance)
    {
        targetPosition = default;
        distance = float.MaxValue;
        var found = false;
        foreach (var pawn in _targets.ToArray())
        {
            try
            {
                if (!pawn.IsValid() || !pawn.IsAlive)
                {
                    continue;
                }

                var candidate = pawn.GetAbsOrigin();
                var dx = candidate.X - origin.X;
                var dy = candidate.Y - origin.Y;
                var candidateDistance = MathF.Sqrt((dx * dx) + (dy * dy));
                if (candidateDistance >= distance)
                {
                    continue;
                }

                found = true;
                distance = candidateDistance;
                targetPosition = candidate;
            }
            catch
            {
                // Ignore a pawn removed during this update.
            }
        }

        return found;
    }

    private void ScheduleThink(IBaseAnimGraph entity)
    {
        try
        {
            entity.AnimGraphUpdateEnabled = true;
            entity.NextThinkTick = Math.Max(1, _modSharp.GetGlobals().TickCount + 1);
        }
        catch
        {
        }
    }

    private static bool IsAvailable(IBaseAnimGraph entity)
    {
        try
        {
            return !entity.IsDisposed
                   && entity.IsValid()
                   && !entity.IsMarkedForDeletion();
        }
        catch
        {
            return false;
        }
    }

    private static void Destroy(IBaseAnimGraph entity)
    {
        try
        {
            if (IsAvailable(entity))
            {
                entity.Kill();
            }
        }
        catch
        {
        }
    }

    private static float NormalizeYaw(float value)
    {
        value %= 360.0f;
        return value < -180.0f
            ? value + 360.0f
            : value > 180.0f
                ? value - 360.0f
                : value;
    }

    private sealed class TrackedNpc
    {
        internal TrackedNpc(
            int id,
            NpcPresentationSpec spec,
            IBaseAnimGraph entity,
            double createdAt,
            double materializationDeadline)
        {
            Id = id;
            Spec = spec;
            Entity = entity;
            LastUpdateAt = createdAt;
            NextMaterializationAttempt = createdAt + MaterializationRetrySeconds;
            MaterializationDeadline = materializationDeadline;
        }

        internal int Id { get; }
        internal NpcPresentationSpec Spec { get; }
        internal IBaseAnimGraph Entity { get; }
        internal double LastUpdateAt { get; set; }
        internal double NextMaterializationAttempt { get; set; }
        internal double MaterializationDeadline { get; }
        internal bool ControllerReady { get; set; }
        internal bool IsMoving { get; set; }
        internal string LastAg2Status { get; set; } = "spawned";
    }
}
