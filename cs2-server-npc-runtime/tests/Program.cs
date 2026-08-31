using System.Numerics;
using Cs2ServerNpcRuntimeExample;

namespace Cs2ServerNpcRuntimeTests;

internal static class Program
{
    private static readonly NpcIdentity Identity = new(17, 42, 3);
    private static readonly RouteSnapshot NoRoute = new(
        RouteStatus.None,
        Identity,
        null,
        Vector3.Zero,
        Vector3.Zero,
        0,
        0,
        0);

    public static void Main()
    {
        PresentationFailureRetriesAttackEdge();
        LateImpactExpiresWithoutDamage();
        BodyLossCancelsAndForgetsManagedOwnership();
        BodyLossCleanupRetriesAreBounded();
        CleanupStateIgnoresLateDamage();
        StopFailureDoesNotRewriteACommittedImpact();
        DeathDoesNotRewriteACommittedImpact();
        RouteRequiresAnExplicitPositiveSerial();
        ArrivedMotorReceiptStopsTheBody();
        Console.WriteLine("ServerNpcRuntimeSkeleton smoke tests passed.");
    }

    private static void PresentationFailureRetriesAttackEdge()
    {
        var fixture = CreateReadyAgent();
        fixture.Presentation.FailuresRemaining = 1;

        fixture.Agent.Tick(0.02, 0.01f, AttackTarget(), 0, NoRoute);
        fixture.Agent.Tick(0.03, 0.01f, AttackTarget(), 0, NoRoute);

        Check(fixture.Presentation.Attempts == 3, "presentation retry count");
        Check(fixture.Presentation.Successes[^1].AttackEntryPulse, "attack pulse survived one adapter failure");
        Check(fixture.Presentation.Successes[^1].StateEntry, "state-entry edge survived one adapter failure");
        Check(fixture.Agent.PresentationHealthy, "presentation health recovered after retry");
    }

    private static void LateImpactExpiresWithoutDamage()
    {
        var fixture = CreateReadyAgent();
        fixture.Agent.Tick(0.02, 0.01f, AttackTarget(), 0, NoRoute);
        fixture.Agent.Tick(1.0, 0.01f, AttackTarget(), 0, NoRoute);

        Check(fixture.Combat.Calls == 0, "late host tick must not commit damage");
        Check(fixture.Agent.LastImpactStatus == ImpactStatus.Expired, "late impact exposes Expired");
    }

    private static void BodyLossCancelsAndForgetsManagedOwnership()
    {
        var fixture = CreateReadyAgent();
        fixture.Body.Current = false;
        fixture.Agent.Tick(0.02, 0.01f, null, 0, NoRoute);

        Check(fixture.Agent.Phase == NpcPhase.Removed, "body loss is terminal");
        Check(fixture.Ownership.CancelCalls == 1, "body loss cancels managed work");
        Check(fixture.Ownership.CleanupCalls == 1, "body loss attempts active owned-resource cleanup");
        Check(fixture.Ownership.ForgetBodyLostCalls == 1, "body loss forgets managed indexes");
    }

    private static void BodyLossCleanupRetriesAreBounded()
    {
        var fixture = CreateReadyAgent();
        fixture.Body.Current = false;
        fixture.Ownership.CleanupResults.Enqueue(false);
        fixture.Ownership.CleanupResults.Enqueue(false);
        fixture.Ownership.CleanupResults.Enqueue(false);

        fixture.Agent.Tick(0.02, 0.01f, null, 0, NoRoute);
        Check(fixture.Agent.Phase == NpcPhase.CleanupPending, "failed cleanup remains retryable");
        Check(fixture.Ownership.ForgetBodyLostCalls == 0, "failed cleanup retains ownership");
        fixture.Agent.Tick(0.13, 0.01f, null, 0, NoRoute);
        fixture.Agent.Tick(0.24, 0.01f, null, 0, NoRoute);

        Check(fixture.Agent.Phase == NpcPhase.CleanupFailed, "cleanup stops after its configured retry bound");
        Check(fixture.Agent.CleanupAttempts == 3, "cleanup retry limit is exact");
        Check(fixture.Ownership.ForgetBodyLostCalls == 0, "exhausted cleanup preserves ownership for remediation");
    }

    private static void CleanupStateIgnoresLateDamage()
    {
        var fixture = CreateReadyAgent();
        fixture.Body.Current = false;
        fixture.Ownership.CleanupResults.Enqueue(false);
        fixture.Agent.Tick(0.02, 0.01f, null, 0, NoRoute);
        fixture.Agent.CommitValidatedDamage(1_000, 0.03);

        Check(fixture.Agent.Phase == NpcPhase.CleanupPending, "late damage cannot escape cleanup state");
    }

    private static void StopFailureDoesNotRewriteACommittedImpact()
    {
        var fixture = CreateReadyAgent();
        fixture.Agent.Tick(0.02, 0.01f, AttackTarget(), 0, NoRoute);
        fixture.Agent.Tick(0.13, 0.01f, AttackTarget(), 0, NoRoute);
        Check(fixture.Agent.LastImpactStatus == ImpactStatus.Committed, "impact committed before stop failure");
        fixture.Body.StopResult = StopStatus.Failed;
        fixture.Agent.Tick(0.135, 0.005f, AttackTarget(), 0, NoRoute);

        Check(fixture.Agent.LastImpactStatus == ImpactStatus.Committed, "stop failure preserves committed impact receipt");
    }

    private static void DeathDoesNotRewriteACommittedImpact()
    {
        var fixture = CreateReadyAgent();
        fixture.Agent.Tick(0.02, 0.01f, AttackTarget(), 0, NoRoute);
        fixture.Agent.Tick(0.13, 0.01f, AttackTarget(), 0, NoRoute);
        fixture.Agent.CommitValidatedDamage(1_000, 0.135);

        Check(fixture.Agent.Phase == NpcPhase.Dead, "lethal damage enters Dead");
        Check(fixture.Agent.LastImpactStatus == ImpactStatus.Committed, "death preserves committed impact receipt");
    }

    private static void RouteRequiresAnExplicitPositiveSerial()
    {
        var fixture = CreateReadyAgent();
        var unsolicited = NoRoute with
        {
            Status = RouteStatus.Success,
            NextContact = new Vector3(64, 0, 0),
        };
        fixture.Agent.Tick(0.02, 0.01f, null, 0, unsolicited);

        Check(fixture.Agent.LastRouteStatus == RouteStatus.Superseded, "unsolicited serial-zero route is rejected");
        Check(fixture.Body.MoveCalls == 0, "rejected route cannot move the body");
    }

    private static void ArrivedMotorReceiptStopsTheBody()
    {
        var fixture = CreateReadyAgent();
        fixture.Agent.ExpectRoute(1, 7);
        fixture.Body.NextMotor = new MotorReceipt(
            MotorStatus.Arrived,
            new Vector3(10, 0, 0),
            new Vector3(4, 0, 0));
        var route = NoRoute with
        {
            Status = RouteStatus.Success,
            NextContact = new Vector3(64, 0, 0),
            RequestSerial = 1,
            BlockerRevision = 7,
            ProducedAt = 0.01,
        };
        var stopsBefore = fixture.Body.StopCalls;
        fixture.Agent.Tick(0.02, 0.01f, null, 7, route);

        Check(fixture.Agent.LastMotorStatus == MotorStatus.Arrived, "Arrived status is retained");
        Check(fixture.Agent.Phase == NpcPhase.Idle, "Arrived enters Idle");
        Check(fixture.Body.StopCalls == stopsBefore + 1, "Arrived explicitly stops residual velocity");
    }

    private static Fixture CreateReadyAgent()
    {
        var body = new FakeBody();
        var combat = new FakeCombat();
        var presentation = new FakePresentation();
        var ownership = new FakeOwnership();
        var diagnostics = new FakeDiagnostics();
        var profile = new NpcProfile(
            MaxHealth: 100,
            MoveSpeed: 200,
            AttackRange: 96,
            MinimumFacingDot: 0.5f,
            AttackRequiresLineOfSight: true,
            AttackDamage: 20,
            MaximumImpactLateness: 0.02,
            MaximumRouteAge: 0.5,
            MaximumTargetDrift: 32,
            SpawnDuration: 0,
            AttackWindup: 0.1,
            AttackActive: 0.1,
            AttackRecovery: 0.2,
            DeathPresentationDuration: 0.5,
            CleanupRetryLimit: 3,
            CleanupRetryInterval: 0.1);
        var agent = new ServerNpcAgent(
            Identity,
            profile,
            body,
            combat,
            presentation,
            ownership,
            diagnostics);
        agent.NotifyMaterialized(0);
        agent.Tick(0.01, 0.01f, null, 0, NoRoute);
        return new Fixture(agent, body, combat, presentation, ownership, diagnostics);
    }

    private static TargetSnapshot AttackTarget() => new(
        new NpcIdentity(31, 9, Identity.WorldGeneration),
        IsAlive: true,
        IsHostile: true,
        HasLineOfSight: true,
        Distance: 48,
        FacingDot: 1,
        NavigationPoint: new Vector3(48, 0, 0),
        AimPoint: new Vector3(48, 0, 32),
        Revision: 1);

    private static void Check(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException($"Assertion failed: {message}");
    }

    private sealed record Fixture(
        ServerNpcAgent Agent,
        FakeBody Body,
        FakeCombat Combat,
        FakePresentation Presentation,
        FakeOwnership Ownership,
        FakeDiagnostics Diagnostics);

    private sealed class FakeBody : IBodyPort
    {
        public bool Current { get; set; } = true;
        public StopStatus StopResult { get; set; } = StopStatus.Stopped;
        public MotorReceipt NextMotor { get; set; } = new(MotorStatus.Moved, Vector3.Zero, Vector3.Zero);
        public int MoveCalls { get; private set; }
        public int StopCalls { get; private set; }

        public bool IsCurrent(NpcIdentity identity) => Current;

        public MotorReceipt MoveToward(NpcIdentity identity, Vector3 nextContact, float speed, float deltaSeconds)
        {
            MoveCalls++;
            return NextMotor;
        }

        public StopStatus Stop(NpcIdentity identity)
        {
            StopCalls++;
            return StopResult;
        }
        public bool TryRemove(NpcIdentity identity) => true;
    }

    private sealed class FakeCombat : ICombatPort
    {
        public int Calls { get; private set; }

        public ImpactStatus CommitImpact(
            NpcIdentity attacker,
            NpcIdentity target,
            long actionToken,
            in ImpactPolicy policy)
        {
            Calls++;
            return ImpactStatus.Committed;
        }
    }

    private sealed class FakePresentation : IPresentationPort
    {
        public int FailuresRemaining { get; set; }
        public int Attempts { get; private set; }
        public List<PresentationSnapshot> Successes { get; } = [];

        public PresentationStatus Apply(in PresentationSnapshot snapshot)
        {
            Attempts++;
            if (FailuresRemaining-- > 0)
                throw new InvalidOperationException("simulated adapter failure");
            Successes.Add(snapshot);
            return PresentationStatus.Applied;
        }
    }

    private sealed class FakeOwnership : IOwnershipPort
    {
        public int CancelCalls { get; private set; }
        public int CleanupCalls { get; private set; }
        public int ForgetBodyLostCalls { get; private set; }
        public Queue<bool> CleanupResults { get; } = new();

        public void CancelManagedWork(NpcIdentity identity) => CancelCalls++;

        public bool TryCleanupActive(NpcIdentity identity)
        {
            CleanupCalls++;
            return CleanupResults.Count == 0 || CleanupResults.Dequeue();
        }

        public void ForgetBodyLost(NpcIdentity identity) => ForgetBodyLostCalls++;
        public void ForgetWorld(NpcIdentity identity) { }
    }

    private sealed class FakeDiagnostics : IRuntimeDiagnostics
    {
        public List<string> Stages { get; } = [];
        public void Report(string stage, Exception error) => Stages.Add(stage);
    }
}
