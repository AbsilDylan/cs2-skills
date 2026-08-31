using System;
using System.Globalization;
using Microsoft.Extensions.Configuration;
using ModSharpAg2NpcExample.Animation;
using ModSharpAg2NpcExample.Npc;
using Sharp.Shared;
using Sharp.Shared.Enums;
using Sharp.Shared.Listeners;
using Sharp.Shared.Managers;
using Sharp.Shared.Objects;
using Sharp.Shared.Types;

namespace ModSharpAg2NpcExample;

public sealed class Ag2NpcExampleModule : IModSharpModule, IGameListener
{
    private const string CommandName = "ag2npc";
    private const string GameDataFile = "modsharp-ag2-npc-example.games.jsonc";

    private readonly IModSharp _modSharp;
    private readonly IClientManager _clients;
    private readonly IEntityManager _entities;
    private IGameData? _gameData;
    private bool _gameDataRegistered;
    private Ag2ParameterWriter? _writer;
    private DirectChaseNpcRuntime? _runtime;

    public Ag2NpcExampleModule(
        ISharedSystem sharedSystem,
        string dllPath,
        string sharpPath,
        Version version,
        IConfiguration coreConfiguration,
        bool hotReload)
    {
        _modSharp = sharedSystem.GetModSharp();
        _clients = sharedSystem.GetClientManager();
        _entities = sharedSystem.GetEntityManager();
    }

    public string DisplayName => "ModSharp AG2 NPC Example";
    public string DisplayAuthor => "Example contributors";
    public int ListenerVersion => IGameListener.ApiVersion;
    public int ListenerPriority => 0;

    public bool Init()
    {
        _gameData = _modSharp.GetGameData();
        try
        {
            _gameData.Register(GameDataFile);
            _gameDataRegistered = true;
            _writer = Ag2ParameterWriter.Resolve(_modSharp, _gameData);
        }
        catch (Exception exception)
        {
            // Register() records the path before native parsing. Remove that
            // bookkeeping entry as well as any partial native registration.
            try
            {
                _gameData.Unregister(GameDataFile);
            }
            catch
            {
                // The original registration error is the useful status.
            }

            _writer = Ag2ParameterWriter.Unavailable(
                $"gamedata-register-error:{exception.GetType().Name}");
        }

        _runtime = new DirectChaseNpcRuntime(_modSharp, _entities, _writer);
        _modSharp.InstallGameListener(this);
        _clients.InstallCommandCallback(CommandName, OnCommand);
        _modSharp.InstallGameFrameHook(null, OnGameFramePost);
        _modSharp.LogMessage($"[AG2 NPC Example] Loaded. {_writer.Describe()}");
        return true;
    }

    public void Shutdown()
    {
        _runtime?.Clear(destroyEntities: true);
        _modSharp.RemoveGameFrameHook(null, OnGameFramePost);
        _clients.RemoveCommandCallback(CommandName, OnCommand);
        _modSharp.RemoveGameListener(this);
        if (_gameDataRegistered && _gameData is not null)
        {
            try
            {
                _gameData.Unregister(GameDataFile);
            }
            catch (Exception exception)
            {
                _modSharp.LogWarning(
                    $"[AG2 NPC Example] Could not unregister gamedata: {exception.GetType().Name}.");
            }
        }

        _gameDataRegistered = false;
        _modSharp.LogMessage("[AG2 NPC Example] Unloaded.");
    }

    public void OnResourcePrecache()
    {
        foreach (var spec in NpcCatalog.All)
        {
            try
            {
                _modSharp.PrecacheResource(spec.Model);
            }
            catch (Exception exception)
            {
                _modSharp.LogWarning(
                    $"[AG2 NPC Example] Could not precache {spec.Model}: {exception.GetType().Name}.");
            }
        }
    }

    public void OnRoundRestart()
        => _runtime?.Clear(destroyEntities: true);

    public void OnGameDeactivate()
        // During map teardown Source 2 owns entity deletion; forget wrappers.
        => _runtime?.Clear(destroyEntities: false);

    private void OnGameFramePost(bool simulating, bool firstTick, bool lastTick)
        => _runtime?.Update(simulating);

    private ECommandAction OnCommand(IGameClient client, StringCommand command)
    {
        var action = command.ArgCount > 0
            ? command.GetArg(1).Trim()
            : "help";
        if (action.Equals("help", StringComparison.OrdinalIgnoreCase))
        {
            PrintHelp(client);
            return ECommandAction.Stopped;
        }

        if (action.Equals("status", StringComparison.OrdinalIgnoreCase))
        {
            client.ConsolePrint(
                $"[AG2 NPC] active={_runtime?.ActiveCount ?? 0}; {_runtime?.NativeStatus ?? "runtime unavailable"}");
            return ECommandAction.Stopped;
        }

        if (action.Equals("clear", StringComparison.OrdinalIgnoreCase))
        {
            var count = _runtime?.ActiveCount ?? 0;
            _runtime?.Clear(destroyEntities: true);
            client.ConsolePrint($"[AG2 NPC] removed {count} NPC(s).");
            return ECommandAction.Stopped;
        }

        if (_runtime is null || !_runtime.CanSpawn)
        {
            client.ConsolePrint(
                $"[AG2 NPC] native AG2 bridge disabled: {_runtime?.NativeStatus ?? "runtime unavailable"}");
            return ECommandAction.Stopped;
        }

        if (!NpcCatalog.TryFind(action, out var spec))
        {
            client.ConsolePrint($"[AG2 NPC] unknown model '{action}'.");
            PrintHelp(client);
            return ECommandAction.Stopped;
        }

        var controller = client.GetPlayerController();
        var pawn = controller?.GetPlayerPawn();
        if (pawn is null || !pawn.IsValid() || !pawn.IsAlive)
        {
            client.ConsolePrint("[AG2 NPC] you need a living player pawn to spawn around.");
            return ECommandAction.Stopped;
        }

        var count = 1;
        if (command.ArgCount > 1
            && (!int.TryParse(
                    command.GetArg(2),
                    NumberStyles.Integer,
                    CultureInfo.InvariantCulture,
                    out count)
                || count is < 1 or > 8))
        {
            client.ConsolePrint("[AG2 NPC] count must be between 1 and 8.");
            return ECommandAction.Stopped;
        }

        var result = _runtime.SpawnAround(pawn, spec, count);
        client.ConsolePrint($"[AG2 NPC] {result.Status}.");
        return ECommandAction.Stopped;
    }

    private static void PrintHelp(IGameClient client)
    {
        client.ConsolePrint("[AG2 NPC] !ag2npc shambler [1-8]");
        client.ConsolePrint("[AG2 NPC] !ag2npc amber [1-8]");
        client.ConsolePrint("[AG2 NPC] !ag2npc sapphire [1-8]");
        client.ConsolePrint("[AG2 NPC] !ag2npc status | !ag2npc clear");
    }
}
