#!/usr/bin/env python3
"""Compile authored CS2 assets in a new addon; Python 3.10+ standard library only."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import threading
import time
from typing import Callable, Sequence
import uuid


STAGED_EXTENSIONS = frozenset({
    '.vpcf', '.vtex', '.vmat', '.vmdl', '.mks', '.tga', '.png', '.jpg', '.jpeg',
    '.webp', '.bmp', '.tif', '.tiff', '.psd', '.exr', '.hdr', '.dmx', '.fbx',
    '.obj', '.smd', '.vdata',
})
COMPILE_ORDER = {'.vtex': 0, '.vmat': 1, '.vmdl': 2, '.vpcf': 3}
DEVICE_NAME = re.compile(r'^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', re.I)
RESOURCE_LITERAL = re.compile(r'\bresource\s*:\s*("(?:\\.|[^"\\])*")')
CHILD_LITERAL = re.compile(r'\bm_ChildRef\s*=\s*(?:resource\s*:\s*)?("(?:\\.|[^"\\])*")')


@dataclass(frozen=True)
class Config:
    cs2_root: Path
    source_root: Path
    work_root: Path
    effect_root: str | None = None
    inputs: tuple[str, ...] = ()
    timeout: float = 45.0
    total_timeout: float = 180.0
    max_output_bytes: int = 65536
    max_files: int = 128
    max_source_bytes: int = 64 * 1024 * 1024
    max_compiled_bytes: int = 128 * 1024 * 1024
    expected_compiler_sha256: str | None = None
    viewer_cli: Path | None = None
    allow_external_particles: bool = False


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    output: bytes
    output_bytes_seen: int
    truncated: bool
    reader_incomplete: bool = False


Runner = Callable[[Path, Sequence[str], Path, float, int], ProcessResult]


def run_process(executable: Path, arguments: Sequence[str], cwd: Path,
                timeout: float, max_output_bytes: int) -> ProcessResult:
    """Drain combined output while retaining at most the requested byte budget."""
    process = subprocess.Popen(
        [str(executable), *arguments], cwd=str(cwd), shell=False,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0,
    )
    retained = bytearray()
    seen = 0

    def drain() -> None:
        nonlocal seen
        assert process.stdout is not None
        try:
            while chunk := process.stdout.read(8192):
                seen += len(chunk)
                available = max(0, max_output_bytes - len(retained))
                retained.extend(chunk[:available])
        finally:
            process.stdout.close()

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        exit_code = process.wait(timeout=10)
    reader.join(timeout=2)
    return ProcessResult(exit_code, timed_out, bytes(retained), seen,
                         seen > max_output_bytes, reader.is_alive())


def absolute(value: Path, label: str) -> Path:
    if not value.is_absolute() or '\0' in str(value):
        raise ValueError(f'{label} must be an explicit absolute path')
    return Path(os.path.abspath(value))


def reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def safe_existing(target: Path, directory: bool) -> None:
    current = Path(target.anchor)
    parts = target.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        info = current.lstat()
        if reparse(info) or os.path.normcase(str(current.resolve(strict=True))) != os.path.normcase(str(current)):
            raise ValueError('Refusing a symbolic link, junction, reparse point or redirected realpath')
        expected_directory = index < len(parts) - 1 or directory
        if expected_directory and not stat.S_ISDIR(info.st_mode):
            raise ValueError('Expected a directory in a native compile path')
        if not expected_directory and not stat.S_ISREG(info.st_mode):
            raise ValueError('Expected a regular file in a native compile path')


def ensure_directory(target: Path) -> None:
    try:
        safe_existing(target, True)
        return
    except FileNotFoundError:
        pass
    if target.parent == target:
        raise ValueError('Cannot create a filesystem root')
    ensure_directory(target.parent)
    try:
        target.mkdir()
    except FileExistsError:
        pass
    safe_existing(target, True)


def below(parent: Path, relative: str) -> Path:
    result = parent.joinpath(*PurePosixPath(relative).parts)
    result.relative_to(parent)
    return result


def canonical_resource(value: str) -> str:
    if not value or len(value) > 512 or not re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_./-]*', value):
        raise ValueError('Unsafe or non-relative resource path')
    if any(part in ('', '.', '..') or DEVICE_NAME.match(part) for part in value.split('/')):
        raise ValueError('Traversal, empty segments or Windows device names in resource path')
    return value.lower()


def sha256_file(target: Path) -> str:
    safe_existing(target, False)
    digest = hashlib.sha256()
    with target.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def small_text(target: Path, limit: int) -> str:
    safe_existing(target, False)
    if target.stat().st_size > limit:
        raise ValueError('Installation identity file exceeds its size budget')
    return target.read_text(encoding='utf-8-sig', errors='strict')


def fresh_write(target: Path, payload: bytes) -> None:
    safe_existing(target.parent, True)
    with target.open('xb') as stream:
        stream.write(payload)
    safe_existing(target, False)


def overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def portable_message(value: str, prepared: dict) -> str:
    for name, marker in (('source', '<source>'), ('work', '<work>'), ('cs2', '<cs2>')):
        value = re.sub(re.escape(str(prepared[name])), lambda _: marker, value,
                       flags=re.I if os.name == 'nt' else 0)
    return value


def audit_output_tree(directory: Path, byte_limit: int, file_limit: int) -> dict:
    """Count dependency outputs too; this is scoped to the fresh game addon."""
    safe_existing(directory, True)
    files = []
    total = 0
    for parent, directories, names in os.walk(directory, followlinks=False):
        for name in directories:
            safe_existing(Path(parent) / name, True)
        for name in names:
            output = Path(parent) / name
            safe_existing(output, False)
            size = output.stat().st_size
            total += size
            if len(files) + 1 > file_limit or total > byte_limit:
                raise RuntimeError('Fresh game-addon output tree, including dependencies, exceeds its budget')
            files.append({'path': output.relative_to(directory).as_posix(), 'bytes': size})
    return {'scope': 'fresh-game-addon-only', 'files': sorted(files, key=lambda item: item['path']), 'totalBytes': total}


def prepare(config: Config) -> dict:
    if not (1 <= config.max_files <= 4096 and 1 <= config.max_source_bytes <= 4096 * 1024 * 1024
            and 16 <= config.max_compiled_bytes <= 4096 * 1024 * 1024
            and 1 <= config.timeout <= 3600 and 1 <= config.total_timeout <= 14400
            and 1024 <= config.max_output_bytes <= 16 * 1024 * 1024):
        raise ValueError('Operational limits are out of range')
    cs2 = absolute(config.cs2_root, 'CS2 root')
    source = absolute(config.source_root, 'Source root')
    work = absolute(config.work_root, 'Work root')
    safe_existing(cs2, True)
    safe_existing(source, True)
    if overlaps(source, work) or cs2 == work or cs2 in work.parents:
        raise ValueError('Use work logs outside the installation and separate from the source tree')
    # Existing ancestors are checked even when the final work directory is new.
    ancestor = work
    while not ancestor.exists():
        if ancestor.is_symlink():
            raise ValueError('Refusing a redirected work directory')
        ancestor = ancestor.parent
    safe_existing(ancestor, True)
    compiler = cs2 / 'game/bin/win64/resourcecompiler.exe'
    game = cs2 / 'game/csgo'
    content_parent = cs2 / 'content/csgo_addons'
    game_parent = cs2 / 'game/csgo_addons'
    for directory in (game, content_parent, game_parent):
        safe_existing(directory, True)
    safe_existing(compiler, False)
    with compiler.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Configured resourcecompiler.exe has no Windows executable header')
    info = dict(line.split('=', 1) for line in small_text(game / 'steam.inf', 65536).splitlines() if '=' in line)
    if info.get('appID') != '730' or info.get('ProductName') != 'cs2':
        raise ValueError('This helper requires CS2 app 730; it does not target Deadlock or another Source 2 game')
    if not re.search(r'"?GameInfo"?\s*\{', small_text(game / 'gameinfo.gi', 2 * 1024 * 1024), re.I):
        raise ValueError('Unrecognized CS2 gameinfo.gi')
    compiler_hash = sha256_file(compiler)
    if config.expected_compiler_sha256 and not re.fullmatch(r'[a-fA-F0-9]{64}', config.expected_compiler_sha256):
        raise ValueError('The pinned compiler fingerprint must be a 64-digit SHA-256')
    if config.expected_compiler_sha256 and compiler_hash != config.expected_compiler_sha256.lower():
        raise ValueError('Compiler SHA-256 does not match the explicitly pinned fingerprint')
    if len(cs2.parents) > 1:
        manifest = cs2.parents[1] / 'appmanifest_730.acf'
        if manifest.exists():
            manifest_text = small_text(manifest, 1024 * 1024)
            found_build = re.search(r'"buildid"\s*"([0-9]+)"', manifest_text, re.I)
            if found_build:
                info['steamBuildId'] = found_build.group(1)
    modules = []
    for name in ('resourcecompiler.dll', 'particles.dll', 'resourcesystem.dll'):
        module = compiler.parent / name
        if module.exists():
            modules.append({'path': f'game/bin/win64/{name}', 'sha256': sha256_file(module), 'bytes': module.stat().st_size})
    viewer = absolute(config.viewer_cli, 'Viewer CLI') if config.viewer_cli is not None else None
    if viewer is not None:
        safe_existing(viewer, False)
    inventory = []
    ignored_files = []
    paths: dict[str, Path] = {}
    total = 0
    for parent, directories, files in os.walk(source, followlinks=False):
        for name in directories:
            safe_existing(Path(parent) / name, True)
        for name in files:
            original = Path(parent) / name
            safe_existing(original, False)
            if original.suffix.lower() in {'.md', '.json', '.txt'}:
                ignored_files.append(original.relative_to(source).as_posix())
                continue
            relative = canonical_resource(original.relative_to(source).as_posix())
            if original.suffix.lower() not in STAGED_EXTENSIONS:
                raise ValueError(f'Unsupported staged file extension: {relative}; use a source-only asset folder')
            if relative in paths:
                raise ValueError(f'Duplicate case-normalized resource: {relative}')
            total += original.stat().st_size
            if len(paths) + 1 > config.max_files or total > config.max_source_bytes:
                raise ValueError('Asset source count/size exceeds the configured operational budget')
            paths[relative] = original
            inventory.append({'path': relative, 'bytes': original.stat().st_size, 'sha256': sha256_file(original)})
    if not paths:
        raise ValueError('No asset sources were found')
    chosen = [canonical_resource(value) for value in config.inputs] if config.inputs else list(paths)
    if len(set(chosen)) != len(chosen):
        raise ValueError('Duplicate explicit compiler input')
    for relative in chosen:
        if relative not in paths:
            raise ValueError('Explicit compiler input is not included in SourceRoot')
        if config.inputs and Path(relative).suffix not in COMPILE_ORDER:
            raise ValueError('Explicit compiler inputs must be .vtex, .vmat, .vmdl or .vpcf definitions')
    chosen = sorted((value for value in chosen if Path(value).suffix in COMPILE_ORDER),
                    key=lambda value: (COMPILE_ORDER[Path(value).suffix], value))
    if not chosen:
        raise ValueError('No .vtex, .vmat, .vmdl or .vpcf compiler inputs were selected')
    if config.effect_root:
        effect_root = canonical_resource(config.effect_root)
        if not effect_root.endswith('.vpcf') or effect_root not in paths:
            raise ValueError('Effect root must name an included .vpcf')
        if effect_root not in chosen:
            raise ValueError('Effect root must also be selected for native compilation')
    references: set[str] = set()
    for relative, original in paths.items():
        if original.suffix.lower() != '.vpcf':
            continue
        text = original.read_text(encoding='utf-8-sig')
        # This is deliberately a conservative literal scan, not a KV3 parser.
        for match in (*RESOURCE_LITERAL.finditer(text), *CHILD_LITERAL.finditer(text)):
            value = json.loads(match.group(1))
            reference = canonical_resource(value)
            references.add(reference)
            particle_source = reference[:-2] if reference.endswith('.vpcf_c') else reference
            if particle_source.endswith('.vpcf') and particle_source not in paths and not config.allow_external_particles:
                raise ValueError(f'Include the referenced particle source or explicitly allow external particles: {particle_source}')
    return {'cs2': cs2, 'source': source, 'work': work, 'compiler': compiler, 'game': game,
            'content_parent': content_parent, 'game_parent': game_parent, 'paths': paths,
            'inventory': sorted(inventory, key=lambda item: item['path']), 'inputs': chosen,
            'ignored_files': sorted(ignored_files),
            'references': sorted(references), 'identity': info, 'compiler_sha256': compiler_hash,
            'modules': modules, 'viewer': viewer}


def compile_assets(config: Config, runner: Runner = run_process,
                   run_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex) -> dict:
    prepared = prepare(config)
    run_id = run_id_factory()
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Invalid generated run identifier')
    addon_name = 's2_particle_validation_' + run_id
    content = prepared['content_parent'] / addon_name
    output = prepared['game_parent'] / addon_name
    session = prepared['work'] / run_id
    for target in (content, output, session):
        if os.path.lexists(target):
            raise ValueError('A fresh addon and report directory are required; refusing to overwrite')
    ensure_directory(prepared['work'])
    session.mkdir()
    (session / 'logs').mkdir()
    content.mkdir()
    report = {
        'schema': 'cs2-native-asset-validation/1', 'performedUtc': datetime.now(timezone.utc).isoformat(),
        'addonName': addon_name, 'game': prepared['identity'],
        'compiler': {'path': 'game/bin/win64/resourcecompiler.exe', 'sha256': prepared['compiler_sha256'],
                     'authenticode': 'not-checked', 'installedModules': prepared['modules']},
        'sourceInventory': prepared['inventory'], 'effectRoot': config.effect_root,
        'selectedInputs': prepared['inputs'], 'ignoredSidecars': prepared['ignored_files'],
        'referenceScan': 'conservative-literal-scan-not-a-complete-KV3-parser',
        'referenceCandidates': prepared['references'],
        'execution': {'nativeCompilation': 'failed', 'propertyRetention': 'not-run',
                      'nativeRuntimeBehavior': 'not-run', 'nativeVisualValidation': 'not-run'},
        'runs': [], 'outputs': [], 'errors': [],
        'warnings': [
            'Compiler acceptance does not establish field retention, asset closure, CP behavior or appearance.',
            'A fresh addon is not an operating-system sandbox; -fshallow can build dependencies as needed.',
            'No game launch, PET automation, launch-setting change or Workshop publication is performed.',
        ],
    }
    started = time.monotonic()
    try:
        expected_hashes = {item['path']: item['sha256'] for item in prepared['inventory']}
        for relative, original in prepared['paths'].items():
            destination = below(content, relative)
            ensure_directory(destination.parent)
            source_bytes = original.read_bytes()
            if hashlib.sha256(source_bytes).hexdigest() != expected_hashes[relative]:
                raise RuntimeError('Original source changed between preflight and staging')
            fresh_write(destination, source_bytes)
        for index, relative in enumerate(prepared['inputs']):
            remaining = config.total_timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('Total effect compilation time budget exceeded')
            source = below(content, relative)
            safe_existing(source, False)
            safe_existing(prepared['compiler'], False)
            safe_existing(prepared['game_parent'], True)
            safe_existing(session, True)
            command = ['-i', str(source), '-game', str(prepared['game']), '-nop4', '-fshallow']
            timestamp = time.time()
            result = runner(prepared['compiler'], command, session,
                            min(config.timeout, remaining), config.max_output_bytes)
            log_name = f'logs/compiler-{index:03d}.log'
            fresh_write(session / log_name, result.output[:config.max_output_bytes])
            run = {'input': relative, 'arguments': ['-i', '<new-addon-content>/' + relative,
                   '-game', '<cs2>/game/csgo', '-nop4', '-fshallow'], 'exitCode': result.exit_code,
                   'timedOut': result.timed_out, 'outputBytesSeen': result.output_bytes_seen,
                   'outputTruncated': result.truncated, 'readerIncomplete': result.reader_incomplete,
                   'log': log_name}
            report['runs'].append(run)
            if result.timed_out or result.exit_code != 0 or result.reader_incomplete:
                raise RuntimeError(f'Compiler failed/timed out for {relative}; inspect {log_name}')
            compiled = below(output, relative + '_c')
            safe_existing(compiled, False)
            info = compiled.stat()
            if info.st_size < 16 or info.st_size > config.max_compiled_bytes or info.st_mtime < timestamp - 2:
                raise RuntimeError(f'Output is stale, empty or exceeds its size budget: {relative}')
            compiled_record = {'source': relative, 'path': f'game/csgo_addons/{addon_name}/{relative}_c',
                               'bytes': info.st_size, 'sha256': sha256_file(compiled), 'fresh': True,
                               'readback': {'status': 'not-run'}}
            report['outputs'].append(compiled_record)
            report['outputTreeAudit'] = audit_output_tree(
                output, config.max_compiled_bytes, max(256, config.max_files * 8))
        for item in prepared['inventory']:
            if sha256_file(prepared['paths'][item['path']]) != item['sha256']:
                raise RuntimeError('Original source changed during compilation')
        report['execution']['nativeCompilation'] = 'passed'
        if prepared['viewer'] is not None:
            report['readbackTool'] = {'sha256': sha256_file(prepared['viewer']),
                                      'arguments': ['-i', '<compiled-resource>', '--block', 'DATA']}
            for index, item in enumerate(report['outputs']):
                remaining = config.total_timeout - (time.monotonic() - started)
                if remaining <= 0:
                    report['warnings'].append('Readback capture stopped at the total time budget')
                    break
                compiled = prepared['cs2'] / item['path']
                safe_existing(compiled, False)
                capture = runner(prepared['viewer'], ['-i', str(compiled), '--block', 'DATA'],
                                 session, min(config.timeout, remaining), config.max_output_bytes)
                log_name = f'logs/readback-{index:03d}.txt'
                fresh_write(session / log_name, capture.output[:config.max_output_bytes])
                item['readback'] = {'status': 'text-captured' if capture.exit_code == 0 and not capture.timed_out and not capture.reader_incomplete else 'failed',
                                    'exitCode': capture.exit_code, 'timedOut': capture.timed_out,
                                    'outputTruncated': capture.truncated, 'readerIncomplete': capture.reader_incomplete, 'log': log_name,
                                    'propertyRetention': 'manual-inspection-required'}
    except Exception as error:
        report['errors'].append(portable_message(f'{type(error).__name__}: {error}', prepared))
    fresh_write(session / 'report.json', (json.dumps(report, indent=2) + '\n').encode('utf-8'))
    return {'report': report, 'report_path': session / 'report.json', 'content_directory': content,
            'output_directory': output}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2-root', type=Path, required=True, help='Absolute CS2 installation root')
    parser.add_argument('--source-root', type=Path, required=True, help='Absolute source-only asset folder')
    parser.add_argument('--work-root', type=Path, required=True, help='Absolute separate folder for new run logs')
    parser.add_argument('--effect-root', help='Optional root .vpcf resource path, relative to source-root')
    parser.add_argument('--input', action='append', default=[], help='Optional explicit compiler input; repeatable')
    parser.add_argument('--timeout', type=float, default=45, help='Seconds per process (default 45)')
    parser.add_argument('--total-timeout', type=float, default=180, help='Total compile/readback seconds (default 180)')
    parser.add_argument('--max-output-kib', type=int, default=64, help='Retained combined output per process')
    parser.add_argument('--max-files', type=int, default=128)
    parser.add_argument('--max-source-mib', type=int, default=64)
    parser.add_argument('--max-compiled-mib', type=int, default=128, help='Maximum aggregate size of compiled outputs')
    parser.add_argument('--expect-compiler-sha256', help='Optional trusted compiler SHA-256 pin')
    parser.add_argument('--viewer-cli', type=Path, help='Optional explicit Source 2 Viewer CLI for DATA text capture')
    parser.add_argument('--allow-external-particles', action='store_true', help='Permit external particle references; weakens closure check')
    parser.add_argument('--plan', action='store_true', help='Inspect installation and sources without creating files or running tools')
    args = parser.parse_args()
    config = Config(args.cs2_root, args.source_root, args.work_root, args.effect_root,
                    tuple(args.input), args.timeout, args.total_timeout,
                    args.max_output_kib * 1024, args.max_files,
                    args.max_source_mib * 1024 * 1024, args.max_compiled_mib * 1024 * 1024,
                    args.expect_compiler_sha256, args.viewer_cli, args.allow_external_particles)
    try:
        if args.plan:
            plan = prepare(config)
            print(json.dumps({'game': plan['identity'], 'compilerSha256': plan['compiler_sha256'],
                              'sourceInventory': plan['inventory'], 'compileOrder': plan['inputs'],
                              'ignoredSidecars': plan['ignored_files'],
                              'referenceCandidates': plan['references'], 'writesPerformed': False}, indent=2))
            return 0
        if os.name != 'nt':
            raise ValueError('Executing resourcecompiler.exe requires Windows; --plan is available for inspection')
        outcome = compile_assets(config)
        status = outcome['report']['execution']['nativeCompilation']
        print(json.dumps({'nativeCompilation': status, 'report': str(outcome['report_path']),
                          'addonName': outcome['report']['addonName'], 'errors': outcome['report']['errors']}, indent=2))
        return 0 if status == 'passed' else 1
    except (OSError, ValueError) as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
