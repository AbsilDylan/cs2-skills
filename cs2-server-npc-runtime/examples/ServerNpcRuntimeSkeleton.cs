// Framework-neutral example for the cs2-server-npc-runtime skill.
// This file contains no ModSharp APIs, signatures, model paths, or game assets.
// Keep Source 2 wrappers inside the port implementations and call Tick only on
// the game thread. Adapt parameter names only from the target model's graph.

using System;
using System.Numerics;

namespace Cs2ServerNpcRuntimeExample;

public readonly record struct NpcIdentity(
    int EntityIndex,
    uint EntitySerial,
    long WorldGeneration);

public enum NpcPhase
{
    Materializing,
    Spawning,
    Idle,
    Moving,
    AttackWindup,
    AttackActive,
    AttackRecovery,
    Dead,
    CleanupPending,
    CleanupFailed,
    Removed,
}

public enum RouteStatus
{
    None,
    Success,
    NoNav,
    StartOutside,
    GoalOutside,
    NoPath,
    Blocked,
    UnsupportedTraversal,
    Pending,
    Cancelled,
    BudgetExceeded,
    Expired,
    Superseded,
    Invalid,
}

public enum MotorStatus
{
    Moved,
    Arrived,
    Blocked,
    Stuck,
    Unsupported,
    Invalid,
}

public enum StopStatus
{
    Stopped,
    AlreadyStopped,
    Failed,
    Invalid,
}

public enum ImpactStatus
{
    None,
    Committed,
    TargetStale,
    OutOfRange,
    Occluded,
    Friendly,
    Cancelled,
    Expired,
    Failed,
}

public enum PresentationStatus
{
    Applied,
    Retry,
    Degraded,
    Invalid,
}

public readonly record struct TargetSnapshot(
    NpcIdentity Identity,
    bool IsAlive,
    bool IsHostile,
    bool HasLineOfSight,
    float Distance,
    float FacingDot,
    Vector3 NavigationPoint,
    Vector3 AimPoint,
    long Revision);

public readonly record struct RouteSnapshot(
    RouteStatus Status,
    NpcIdentity Owner,
    NpcIdentity? Target,
    Vector3 TargetSample,
    Vector3 NextContact,
    long RequestSerial,
    long BlockerRevision,
    double ProducedAt);

public readonly record struct MotorReceipt(
    MotorStatus Status,
    Vector3 DesiredVelocity,
    Vector3 ActualVelocity);

public readonly record struct PresentationSnapshot(
    NpcIdentity Identity,
    NpcPhase Phase,
    Vector3 DesiredVelocity,
    Vector3 ActualVelocity,
    Vector3? AimPoint,
    float HealthFraction,
    long ActionToken,
    long PresentationRevision,
    bool StateEntry,
    bool AttackEntryPulse);

public readonly record struct ImpactPolicy(
    float Range,
    float MinimumFacingDot,
    bool RequireLineOfSight,
    float Damage);

public sealed record NpcProfile(
    float MaxHealth,
    float MoveSpeed,
    float AttackRange,
    float MinimumFacingDot,
    bool AttackRequiresLineOfSight,
    float AttackDamage,
    double MaximumImpactLateness,
    double MaximumRouteAge,
    float MaximumTargetDrift,
    double SpawnDuration,
    double AttackWindup,
    double AttackActive,
    double AttackRecovery,
    double DeathPresentationDuration,
    int CleanupRetryLimit,
    double CleanupRetryInterval)
{
    public void Validate()
    {
        RequireFinitePositive(MaxHealth, nameof(MaxHealth));
        RequireFinitePositive(MoveSpeed, nameof(MoveSpeed));
        RequireFinitePositive(AttackRange, nameof(AttackRange));
        if (!float.IsFinite(MinimumFacingDot) || MinimumFacingDot is < -1 or > 1)
            throw new ArgumentOutOfRangeException(nameof(MinimumFacingDot));
        RequireFinitePositive(AttackDamage, nameof(AttackDamage));
        RequireFiniteNonNegative(MaximumImpactLateness, nameof(MaximumImpactLateness));
        RequireFinitePositive(MaximumRouteAge, nameof(MaximumRouteAge));
        RequireFinitePositive(MaximumTargetDrift, nameof(MaximumTargetDrift));
        RequireFiniteNonNegative(SpawnDuration, nameof(SpawnDuration));
        RequireFiniteNonNegative(AttackWindup, nameof(AttackWindup));
        RequireFiniteNonNegative(AttackActive, nameof(AttackActive));
        RequireFiniteNonNegative(AttackRecovery, nameof(AttackRecovery));
        RequireFiniteNonNegative(DeathPresentationDuration, nameof(DeathPresentationDuration));
        if (CleanupRetryLimit is < 1 or > 100)
            throw new ArgumentOutOfRangeException(nameof(CleanupRetryLimit));
        RequireFinitePositive(CleanupRetryInterval, nameof(CleanupRetryInterval));
    }

    private static void RequireFinitePositive(float value, string name)
    {
        if (!float.IsFinite(value) || value <= 0)
            throw new ArgumentOutOfRangeException(name);
    }

    private static void RequireFiniteNonNegative(double value, string name)
    {
        if (!double.IsFinite(value) || value < 0)
            throw new ArgumentOutOfRangeException(name);
    }

    private static void RequireFinitePositive(double value, string name)
    {
        if (!double.IsFinite(value) || value <= 0)
            throw new ArgumentOutOfRangeException(name);
    }
}

public interface IBodyPort
{
    bool IsCurrent(NpcIdentity identity);
    MotorReceipt MoveToward(NpcIdentity identity, Vector3 nextContact, float speed, float deltaSeconds);
    StopStatus Stop(NpcIdentity identity);
    bool TryRemove(NpcIdentity identity);
}

public interface ICombatPort
{
    // Re-resolve both entities and revalidate life, faction, range, cone and LOS
    // inside this game-thread transaction. Return a typed reason without side
    // effects if any identity or condition is stale.
    ImpactStatus CommitImpact(
        NpcIdentity attacker,
        NpcIdentity target,
        long actionToken,
        in ImpactPolicy policy);
}

public interface IPresentationPort
{
    // An AG2 implementation reacquires the current controller/instance here and
    // uses graph-proven typed setters. A sequence implementation changes clips
    // only on legal state entries. Neither backend owns gameplay state. The
    // adapter must deduplicate retries by identity, presentation revision and
    // action token because an exception may occur after a native side effect.
    PresentationStatus Apply(in PresentationSnapshot snapshot);
}

public interface IOwnershipPort
{
    // This must cancel only managed requests/operators/timers and may be called
    // before active cleanup or world forgetting.
    void CancelManagedWork(NpcIdentity identity);

    // While the native world is active, idempotently stop/remove owned children,
    // particles, sounds and callbacks. Return false to request a bounded retry.
    bool TryCleanupActive(NpcIdentity identity);

    // When the engine has already deleted/recycled the body, remove only
    // managed indexes, listeners and ownership records. Never touch the body.
    void ForgetBodyLost(NpcIdentity identity);

    // After world deactivation, drop managed ownership without native access.
    void ForgetWorld(NpcIdentity identity);
}

public interface IRuntimeDiagnostics
{
    void Report(string stage, Exception error);
}

public sealed class ServerNpcAgent
{
    private readonly NpcProfile _profile;
    private readonly IBodyPort _body;
    private readonly ICombatPort _combat;
    private readonly IPresentationPort _presentation;
    private readonly IOwnershipPort _ownership;
    private readonly IRuntimeDiagnostics _diagnostics;

    private NpcPhase _phase = NpcPhase.Materializing;
    private double _phaseDeadline = double.PositiveInfinity;
    private float _health;
    private Vector3 _desiredVelocity;
    private Vector3 _actualVelocity;
    private TargetSnapshot? _actionTarget;
    private long _actionToken;
    private bool _impactLatched;
    private long _expectedRouteSerial = -1;
    private long _expectedBlockerRevision = -1;
    private long _presentationRevision;
    private long _lastPresentedRevision = -1;
    private long _pendingAttackPulseToken = -1;
    private long _pendingAttackPulseRevision = -1;
    private double _impactDeadline = double.PositiveInfinity;
    private bool _cleanupBodyLost;
    private int _cleanupAttempts;
    private double _nextCleanupAttemptAt = double.PositiveInfinity;

    public ServerNpcAgent(
        NpcIdentity identity,
        NpcProfile profile,
        IBodyPort body,
        ICombatPort combat,
        IPresentationPort presentation,
        IOwnershipPort ownership,
        IRuntimeDiagnostics diagnostics)
    {
        profile.Validate();
        Identity = identity;
        _profile = profile;
        _body = body;
        _combat = combat;
        _presentation = presentation;
        _ownership = ownership;
        _diagnostics = diagnostics;
        _health = profile.MaxHealth;
    }

    public NpcIdentity Identity { get; }
    public NpcPhase Phase => _phase;
    public RouteStatus LastRouteStatus { get; private set; }
    public MotorStatus? LastMotorStatus { get; private set; }
    public ImpactStatus LastImpactStatus { get; private set; }
    public StopStatus LastStopStatus { get; private set; } = StopStatus.AlreadyStopped;
    public PresentationStatus LastPresentationStatus { get; private set; } = PresentationStatus.Applied;
    public bool PresentationHealthy { get; private set; } = true;
    public bool CleanupHealthy { get; private set; } = true;
    public int CleanupAttempts => _cleanupAttempts;

    public void ExpectRoute(long requestSerial, long blockerRevision)
    {
        if (requestSerial > 0 && requestSerial > _expectedRouteSerial && blockerRevision >= 0)
        {
            _expectedRouteSerial = requestSerial;
            _expectedBlockerRevision = blockerRevision;
        }
    }

    public void NotifyMaterialized(double now)
    {
        if (_phase != NpcPhase.Materializing || !double.IsFinite(now))
            return;

        Enter(NpcPhase.Spawning, now + _profile.SpawnDuration);
    }

    // Call only from the one authoritative damage owner after it has validated
    // finite values, attribution and custom-vs-native damage ownership.
    public void CommitValidatedDamage(float damage, double now)
    {
        if (_phase is NpcPhase.Dead or NpcPhase.CleanupPending or
            NpcPhase.CleanupFailed or NpcPhase.Removed ||
            !float.IsFinite(damage) || damage <= 0 || !double.IsFinite(now))
            return;

        _health = MathF.Max(0, _health - damage);
        if (_health <= 0)
            BeginDeath(now);
    }

    public void Tick(
        double now,
        float deltaSeconds,
        TargetSnapshot? perception,
        long currentBlockerRevision,
        in RouteSnapshot route)
    {
        if (_phase == NpcPhase.Removed || !double.IsFinite(now) ||
            !float.IsFinite(deltaSeconds) || deltaSeconds <= 0)
            return;

        if (_phase == NpcPhase.CleanupFailed)
            return;

        if (_phase == NpcPhase.CleanupPending)
        {
            TickCleanup(now);
            return;
        }

        bool bodyIsCurrent;
        try
        {
            bodyIsCurrent = _body.IsCurrent(Identity);
        }
        catch (Exception error)
        {
            ReportSafely("body.identity", error);
            return;
        }

        if (!bodyIsCurrent)
        {
            // The engine already deleted or recycled the body. Do not call a
            // body-native cleanup method through the stale identity. Managed
            // work still has to be cancelled and active-world owned resources
            // receive bounded cleanup retries before indexes are forgotten.
            BeginCleanupAfterBodyLoss(now);
            return;
        }

        var guardedRoute = GuardRoute(now, perception, currentBlockerRevision, route);
        LastRouteStatus = guardedRoute.Status;

        switch (_phase)
        {
            case NpcPhase.Materializing:
                StopSafely();
                break;
            case NpcPhase.Spawning:
                StopSafely();
                if (now >= _phaseDeadline)
                    Enter(NpcPhase.Idle, double.PositiveInfinity);
                break;
            case NpcPhase.Idle:
            case NpcPhase.Moving:
                TickReady(now, deltaSeconds, perception, guardedRoute);
                break;
            case NpcPhase.AttackWindup:
            case NpcPhase.AttackActive:
            case NpcPhase.AttackRecovery:
                TickAttack(now, perception);
                break;
            case NpcPhase.Dead:
                StopSafely();
                if (now >= _phaseDeadline)
                    BeginCleanup(now);
                break;
        }

        if (_phase != NpcPhase.Removed)
            PublishPresentation();
    }

    public void BeginCleanup(double now) => BeginCleanupCore(now, bodyLost: false);

    private void BeginCleanupAfterBodyLoss(double now) =>
        BeginCleanupCore(now, bodyLost: true);

    private void BeginCleanupCore(double now, bool bodyLost)
    {
        if (_phase is NpcPhase.Removed or NpcPhase.CleanupPending or NpcPhase.CleanupFailed ||
            !double.IsFinite(now))
            return;

        _cleanupBodyLost = bodyLost;
        _cleanupAttempts = 0;
        _nextCleanupAttemptAt = now;
        CleanupHealthy = true;
        Enter(NpcPhase.CleanupPending, double.PositiveInfinity);
        if (!bodyLost)
            StopSafely();
        TryPort("ownership.cancel", () => _ownership.CancelManagedWork(Identity));
        TickCleanup(now);
    }

    private void TickCleanup(double now)
    {
        if (_phase != NpcPhase.CleanupPending || now < _nextCleanupAttemptAt)
            return;

        _cleanupAttempts++;

        var ownedResourcesClean = false;
        try
        {
            ownedResourcesClean = _ownership.TryCleanupActive(Identity);
        }
        catch (Exception error)
        {
            ReportSafely("ownership.cleanup", error);
        }

        if (!ownedResourcesClean)
        {
            ScheduleCleanupRetryOrFail(now, "Owned-resource cleanup did not complete.");
            return;
        }

        if (_cleanupBodyLost)
        {
            try
            {
                _ownership.ForgetBodyLost(Identity);
                _phase = NpcPhase.Removed;
            }
            catch (Exception error)
            {
                ReportSafely("ownership.forget-body-lost", error);
                ScheduleCleanupRetryOrFail(now, "Managed body-loss forget failed.");
            }
            return;
        }

        var removed = false;
        try
        {
            removed = _body.TryRemove(Identity);
        }
        catch (Exception error)
        {
            ReportSafely("body.remove", error);
        }

        if (removed)
        {
            _phase = NpcPhase.Removed;
        }
        else
        {
            ScheduleCleanupRetryOrFail(now, "Body removal did not complete.");
        }
    }

    private void ScheduleCleanupRetryOrFail(double now, string reason)
    {
        CleanupHealthy = false;
        if (_cleanupAttempts >= _profile.CleanupRetryLimit)
        {
            Enter(NpcPhase.CleanupFailed, double.PositiveInfinity);
            ReportSafely("cleanup.exhausted", new InvalidOperationException(reason));
            return;
        }

        _nextCleanupAttemptAt = now + _profile.CleanupRetryInterval;
    }

    public void ForgetWorld()
    {
        // Called only after the world-deactivation safety barrier. It performs
        // no body, combat, presentation, timer, or other native operation.
        TryPort("ownership.cancel", () => _ownership.CancelManagedWork(Identity));
        TryPort("ownership.forget", () => _ownership.ForgetWorld(Identity));
        _phase = NpcPhase.Removed;
    }

    private void TickReady(
        double now,
        float deltaSeconds,
        TargetSnapshot? perception,
        in RouteSnapshot route)
    {
        if (IsUsableAttackTarget(perception))
        {
            if (!StopSafely())
            {
                LastImpactStatus = ImpactStatus.Cancelled;
                Enter(NpcPhase.Idle, double.PositiveInfinity);
                return;
            }

            _actionTarget = perception;
            _actionToken++;
            _impactLatched = false;
            LastImpactStatus = ImpactStatus.None;
            _impactDeadline = now + _profile.AttackWindup;
            Enter(NpcPhase.AttackWindup, _impactDeadline);
            _pendingAttackPulseToken = _actionToken;
            _pendingAttackPulseRevision = _presentationRevision;
            return;
        }

        if (route.Status != RouteStatus.Success)
        {
            // No straight-line or teleport fallback. Behavior can inspect
            // LastRouteStatus and decide whether to wait, retarget or despawn.
            Enter(NpcPhase.Idle, double.PositiveInfinity);
            StopSafely();
            return;
        }

        MotorReceipt receipt;
        try
        {
            receipt = _body.MoveToward(Identity, route.NextContact, _profile.MoveSpeed, deltaSeconds);
        }
        catch (Exception error)
        {
            ReportSafely("body.move", error);
            Enter(NpcPhase.Idle, double.PositiveInfinity);
            StopSafely();
            return;
        }

        if (!IsFinite(receipt.DesiredVelocity) || !IsFinite(receipt.ActualVelocity))
        {
            LastRouteStatus = RouteStatus.Invalid;
            ReportSafely("body.move", new InvalidOperationException("Motor returned a non-finite velocity."));
            Enter(NpcPhase.Idle, double.PositiveInfinity);
            StopSafely();
            return;
        }

        _desiredVelocity = receipt.DesiredVelocity;
        _actualVelocity = receipt.ActualVelocity;
        LastMotorStatus = receipt.Status;

        switch (receipt.Status)
        {
            case MotorStatus.Moved:
                Enter(NpcPhase.Moving, double.PositiveInfinity);
                break;
            case MotorStatus.Arrived:
                Enter(NpcPhase.Idle, double.PositiveInfinity);
                StopSafely();
                break;
            case MotorStatus.Blocked:
                Enter(NpcPhase.Idle, double.PositiveInfinity);
                StopSafely();
                break;
            case MotorStatus.Stuck:
                Enter(NpcPhase.Idle, double.PositiveInfinity);
                StopSafely();
                break;
            case MotorStatus.Unsupported:
                Enter(NpcPhase.Idle, double.PositiveInfinity);
                StopSafely();
                break;
            case MotorStatus.Invalid:
            default:
                LastMotorStatus = MotorStatus.Invalid;
                ReportSafely("body.move", new InvalidOperationException("Motor returned an unknown status."));
                Enter(NpcPhase.Idle, double.PositiveInfinity);
                StopSafely();
                break;
        }
    }

    private void TickAttack(double now, TargetSnapshot? perception)
    {
        if (!StopSafely())
        {
            if (!_impactLatched)
            {
                _impactLatched = true;
                LastImpactStatus = ImpactStatus.Cancelled;
            }
            _actionTarget = null;
            Enter(NpcPhase.AttackRecovery, now + _profile.AttackRecovery);
            return;
        }

        // Advance across absolute phase boundaries without rebasing durations on
        // a late host tick. The bound prevents malformed state from looping.
        for (var transition = 0; transition < 4; transition++)
        {
            switch (_phase)
            {
                case NpcPhase.AttackWindup:
                    if (!IsSameUsableTarget(perception, _actionTarget))
                    {
                        _actionTarget = null;
                        LastImpactStatus = ImpactStatus.Cancelled;
                        Enter(NpcPhase.AttackRecovery, now + _profile.AttackRecovery);
                        return;
                    }

                    if (now < _phaseDeadline)
                        return;

                    Enter(NpcPhase.AttackActive, _phaseDeadline + _profile.AttackActive);
                    continue;

                case NpcPhase.AttackActive:
                    var latestImpact = Math.Min(
                        _phaseDeadline,
                        _impactDeadline + _profile.MaximumImpactLateness);
                    if (now <= latestImpact)
                    {
                        CommitImpactOnce();
                    }
                    else if (!_impactLatched)
                    {
                        _impactLatched = true;
                        LastImpactStatus = ImpactStatus.Expired;
                    }
                    if (now < _phaseDeadline)
                        return;

                    Enter(NpcPhase.AttackRecovery, _phaseDeadline + _profile.AttackRecovery);
                    continue;

                case NpcPhase.AttackRecovery:
                    if (now < _phaseDeadline)
                        return;

                    _actionTarget = null;
                    Enter(NpcPhase.Idle, double.PositiveInfinity);
                    return;

                default:
                    return;
            }
        }
    }

    private void CommitImpactOnce()
    {
        if (_impactLatched || _actionTarget is not { } target)
            return;

        // Latch before invoking extension/framework code to prevent reentrant
        // duplicate damage for the same action token.
        _impactLatched = true;
        var policy = new ImpactPolicy(
            _profile.AttackRange,
            _profile.MinimumFacingDot,
            _profile.AttackRequiresLineOfSight,
            _profile.AttackDamage);
        try
        {
            var status = _combat.CommitImpact(
                Identity,
                target.Identity,
                _actionToken,
                policy);
            if (status is ImpactStatus.None || !Enum.IsDefined(status))
            {
                LastImpactStatus = ImpactStatus.Failed;
                ReportSafely("combat.impact", new InvalidOperationException("Combat port returned an invalid impact status."));
            }
            else
            {
                LastImpactStatus = status;
            }
        }
        catch (Exception error)
        {
            LastImpactStatus = ImpactStatus.Failed;
            ReportSafely("combat.impact", error);
        }
    }

    private void BeginDeath(double now)
    {
        if (_phase is NpcPhase.Dead or NpcPhase.Removed)
            return;

        var pendingAttackImpact =
            (_phase is NpcPhase.AttackWindup or NpcPhase.AttackActive) &&
            !_impactLatched;
        _actionToken++;
        _actionTarget = null;
        _impactLatched = true;
        if (pendingAttackImpact)
            LastImpactStatus = ImpactStatus.Cancelled;
        _pendingAttackPulseToken = -1;
        _pendingAttackPulseRevision = -1;
        Enter(NpcPhase.Dead, now + _profile.DeathPresentationDuration);
        TryPort("ownership.cancel", () => _ownership.CancelManagedWork(Identity));
        StopSafely();
    }

    private void PublishPresentation()
    {
        var revision = _presentationRevision;
        var actionToken = _actionToken;
        if (_pendingAttackPulseRevision >= 0 && _pendingAttackPulseRevision != revision)
        {
            // Do not replay an unacknowledged Windup edge in Active/Recovery.
            _pendingAttackPulseToken = -1;
            _pendingAttackPulseRevision = -1;
        }
        var pulse = _pendingAttackPulseToken == actionToken &&
            _pendingAttackPulseRevision == revision;
        var stateEntry = _lastPresentedRevision != revision;
        var snapshot = new PresentationSnapshot(
            Identity,
            _phase,
            _desiredVelocity,
            _actualVelocity,
            _actionTarget?.AimPoint,
            _health / _profile.MaxHealth,
            actionToken,
            revision,
            stateEntry,
            pulse);
        try
        {
            var status = _presentation.Apply(snapshot);
            if (!Enum.IsDefined(status))
                status = PresentationStatus.Invalid;
            LastPresentationStatus = status;
            PresentationHealthy = status == PresentationStatus.Applied;

            if (status is PresentationStatus.Applied or PresentationStatus.Degraded)
            {
                // Only an explicit Applied/Degraded receipt acknowledges the
                // edge. Guards avoid consuming a newer edge after reentrancy.
                if (_presentationRevision == revision)
                    _lastPresentedRevision = revision;
                if (pulse && _pendingAttackPulseToken == actionToken)
                {
                    _pendingAttackPulseToken = -1;
                    _pendingAttackPulseRevision = -1;
                }
            }
            else if (status == PresentationStatus.Invalid)
            {
                ReportSafely("presentation.apply", new InvalidOperationException("Presentation port returned an invalid status."));
            }
        }
        catch (Exception error)
        {
            LastPresentationStatus = PresentationStatus.Retry;
            PresentationHealthy = false;
            ReportSafely("presentation.apply", error);
        }
    }

    private bool IsUsableAttackTarget(TargetSnapshot? candidate) =>
        candidate is { IsAlive: true, IsHostile: true } target &&
        (!_profile.AttackRequiresLineOfSight || target.HasLineOfSight) &&
        float.IsFinite(target.Distance) &&
        target.Distance >= 0 &&
        target.Distance <= _profile.AttackRange &&
        float.IsFinite(target.FacingDot) &&
        target.FacingDot >= _profile.MinimumFacingDot &&
        IsFinite(target.AimPoint);

    private bool IsSameUsableTarget(
        TargetSnapshot? current,
        TargetSnapshot? actionTarget) =>
        current is { IsAlive: true, IsHostile: true } now &&
        (!_profile.AttackRequiresLineOfSight || now.HasLineOfSight) &&
        actionTarget is { } expected &&
        now.Identity == expected.Identity &&
        float.IsFinite(now.Distance) && now.Distance is >= 0 &&
        float.IsFinite(now.FacingDot) &&
        IsFinite(now.NavigationPoint) &&
        IsFinite(now.AimPoint);

    private RouteSnapshot GuardRoute(
        double now,
        TargetSnapshot? perception,
        long currentBlockerRevision,
        in RouteSnapshot route)
    {
        if (_expectedRouteSerial <= 0 ||
            route.Owner != Identity ||
            route.RequestSerial != _expectedRouteSerial)
            return route with { Status = RouteStatus.Superseded };

        if (currentBlockerRevision < 0 ||
            route.BlockerRevision != currentBlockerRevision ||
            route.BlockerRevision != _expectedBlockerRevision)
            return route with { Status = RouteStatus.Superseded };

        if (!double.IsFinite(route.ProducedAt) || route.ProducedAt > now ||
            now - route.ProducedAt > _profile.MaximumRouteAge)
            return route with { Status = RouteStatus.Expired };

        if (route.Target is { } routeTarget &&
            (perception is not { } current || current.Identity != routeTarget))
            return route with { Status = RouteStatus.Superseded };

        if (route.Target is not null &&
            (perception is not { } target ||
             !IsFinite(route.TargetSample) ||
             !IsFinite(target.NavigationPoint) ||
             Vector3.Distance(route.TargetSample, target.NavigationPoint) > _profile.MaximumTargetDrift))
            return route with { Status = RouteStatus.Superseded };

        if (route.Status == RouteStatus.Success && !IsFinite(route.NextContact))
            return route with { Status = RouteStatus.Invalid };

        return route;
    }

    private static bool IsFinite(Vector3 value) =>
        float.IsFinite(value.X) &&
        float.IsFinite(value.Y) &&
        float.IsFinite(value.Z);

    private void Enter(NpcPhase phase, double deadline)
    {
        if (_phase != phase)
            _presentationRevision++;

        _phase = phase;
        _phaseDeadline = deadline;
    }

    private bool StopSafely()
    {
        StopStatus status;
        try
        {
            status = _body.Stop(Identity);
        }
        catch (Exception error)
        {
            LastStopStatus = StopStatus.Failed;
            LastMotorStatus = MotorStatus.Invalid;
            ReportSafely("body.stop", error);
            return false;
        }

        if (status is StopStatus.Stopped or StopStatus.AlreadyStopped)
        {
            LastStopStatus = status;
            _desiredVelocity = Vector3.Zero;
            _actualVelocity = Vector3.Zero;
            return true;
        }

        LastStopStatus = Enum.IsDefined(status) ? status : StopStatus.Invalid;
        LastMotorStatus = MotorStatus.Invalid;
        ReportSafely("body.stop", new InvalidOperationException("Body port did not confirm a stopped motor."));
        return false;
    }

    private void TryPort(string stage, Action operation)
    {
        try
        {
            operation();
        }
        catch (Exception error)
        {
            ReportSafely(stage, error);
        }
    }

    private void ReportSafely(string stage, Exception error)
    {
        try
        {
            _diagnostics.Report(stage, error);
        }
        catch
        {
            // Diagnostics are observers and cannot own the host frame.
        }
    }
}
