#!/usr/bin/env python3
"""Read-only VPK v1/v2 inventory and explicitly selected, CRC-checked extraction.

Python standard library only. This reads the directory tree and original payloads;
it does not decompile Source 2 resources or verify VPK signatures/MD5 sections.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import zlib

SIGNATURE = 0x55AA1234
INLINE_ARCHIVE = 0x7FFF
MAX_TREE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 1_000_000
MAX_STRING_BYTES = 4096
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_EXTRACT_ENTRIES = 64
RESERVED_NAMES = {"con", "prn", "aux", "nul", "conin$", "conout$",
                  *(f"com{i}" for i in "123456789¹²³"), *(f"lpt{i}" for i in "123456789¹²³")}


class VpkError(ValueError):
    pass


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _regular_file(path: Path):
    """Open one non-link regular file and check the descriptor, not only the path."""
    before = path.lstat()
    if _is_link(before) or not stat.S_ISREG(before.st_mode):
        raise VpkError(f"Not a regular non-link file: {path}")
    stream = path.open("rb")
    after = os.fstat(stream.fileno())
    if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        stream.close()
        raise VpkError(f"File changed while opening: {path}")
    return stream


def _read_exact(stream, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise VpkError(f"Truncated VPK: expected {size} bytes, received {len(data)}")
    return data


def _archive_path(value: str, portable: bool = False) -> str:
    if not value or len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise VpkError("Empty or overlong archive path")
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value or ":" in value:
        raise VpkError(f"Unsafe archive path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise VpkError(f"Unsafe archive path: {value!r}")
    if portable and any(
        part.endswith((".", " ")) or any(c in part for c in '<>"|?*')
        or part.split(".", 1)[0].rstrip(" ").casefold() in RESERVED_NAMES for part in parts
    ):
        raise VpkError(f"Archive path cannot be extracted portably: {value!r}")
    return value


@dataclass(frozen=True)
class Entry:
    path: str
    crc32: int
    archive_index: int
    offset: int
    length: int
    preload: bytes

    def metadata(self) -> dict:
        return {
            "path": self.path, "crc32": f"{self.crc32:08x}",
            "archiveIndex": self.archive_index, "offset": self.offset,
            "archiveBytes": self.length, "preloadBytes": len(self.preload),
            "totalBytes": self.length + len(self.preload),
        }


class Vpk:
    def __init__(self, path: Path):
        self.path = Path(path).absolute()
        self.entries: dict[str, Entry] = {}
        self._lookup: dict[str, Entry] = {}
        with _regular_file(self.path) as stream:
            self.file_bytes = os.fstat(stream.fileno()).st_size
            start = _read_exact(stream, 12)
            signature, self.version, tree_size = struct.unpack("<III", start)
            if signature != SIGNATURE or self.version not in (1, 2):
                raise VpkError("Expected a VPK v1/v2 signature and version")
            extra = _read_exact(stream, 16) if self.version == 2 else b""
            self.header_bytes = 12 + len(extra)
            self.data_start = self.header_bytes + tree_size
            if not 1 <= tree_size <= MAX_TREE_BYTES or self.data_start > self.file_bytes:
                raise VpkError("VPK tree size exceeds the file or the 64 MiB limit")
            if self.version == 2:
                sections = struct.unpack("<IIII", extra)
                self.inline_bytes = sections[0]
                if self.data_start + sum(sections) > self.file_bytes:
                    raise VpkError("VPK v2 declared sections exceed the directory file")
            else:
                self.inline_bytes = self.file_bytes - self.data_start
            tree = _read_exact(stream, tree_size)
        self.index_sha256 = hashlib.sha256(start + extra + tree).hexdigest()
        self.index_bytes = self.header_bytes + tree_size
        self._parse_tree(tree)

    def _parse_tree(self, tree: bytes):
        cursor = 0

        def string() -> str:
            nonlocal cursor
            end = tree.find(b"\0", cursor, min(len(tree), cursor + MAX_STRING_BYTES + 1))
            if end < 0:
                raise VpkError("Unterminated or overlong VPK tree string")
            raw = tree[cursor:end]
            cursor = end + 1
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise VpkError("VPK tree path is not UTF-8") from exc

        while True:
            extension = string()
            if not extension:
                break
            if extension != " " and any(c in extension for c in "/\\:."):
                raise VpkError("Invalid VPK extension")
            while True:
                folder = string()
                if not folder:
                    break
                while True:
                    filename = string()
                    if not filename:
                        break
                    if len(self.entries) >= MAX_ENTRIES:
                        raise VpkError("VPK exceeds the entry count limit")
                    if cursor + 18 > len(tree):
                        raise VpkError("Truncated VPK entry metadata")
                    crc, preload_size, archive, offset, length, terminator = struct.unpack_from("<IHHIIH", tree, cursor)
                    cursor += 18
                    if terminator != 0xFFFF or cursor + preload_size > len(tree):
                        raise VpkError("Invalid VPK entry terminator or preload length")
                    preload = tree[cursor:cursor + preload_size]
                    cursor += preload_size
                    basename = filename + ("." + extension if extension != " " else "")
                    archive_path = _archive_path((folder + "/" if folder != " " else "") + basename)
                    # Separators in a filename would create a second spelling of a path.
                    if "/" in filename:
                        raise VpkError("VPK filename contains a directory separator")
                    if archive_path.casefold() in self._lookup:
                        raise VpkError(f"Duplicate or case-aliased VPK entry: {archive_path}")
                    entry = Entry(archive_path, crc, archive, offset, length, preload)
                    self.entries[archive_path] = entry
                    self._lookup[archive_path.casefold()] = entry
        if cursor != len(tree):
            raise VpkError("Unexpected bytes after the VPK tree terminator")

    def provenance(self) -> dict:
        return {
            "directoryFile": self.path.name, "version": self.version,
            "directoryFileBytes": self.file_bytes, "directoryIndexBytes": self.index_bytes,
            "directoryIndexSha256": self.index_sha256,
            "hashScope": "header and directory tree; excludes payload and checksum/signature sections",
            "entryCount": len(self.entries), "signatureVerified": False,
        }

    def find(self, name: str) -> Entry:
        _archive_path(name, portable=True)
        entry = self._lookup.get(name.casefold())
        if entry is None:
            raise VpkError(f"Entry not found: {name}")
        _archive_path(entry.path, portable=True)
        return entry

    def read(self, entry: Entry) -> bytes:
        if entry.length + len(entry.preload) > MAX_ENTRY_BYTES:
            raise VpkError(f"Entry exceeds the 64 MiB extraction limit: {entry.path}")
        if not entry.length:
            if zlib.crc32(entry.preload) != entry.crc32:
                raise VpkError(f"CRC32 mismatch: {entry.path}")
            return entry.preload
        if entry.archive_index == INLINE_ARCHIVE:
            source, offset = self.path, self.data_start + entry.offset
            if entry.offset + entry.length > self.inline_bytes:
                raise VpkError(f"Entry exceeds the inline data section: {entry.path}")
        else:
            if not self.path.name.lower().endswith("_dir.vpk"):
                raise VpkError("External chunks require an explicit *_dir.vpk directory file")
            source = self.path.with_name(self.path.name[:-8] + f"_{entry.archive_index:03d}.vpk")
            offset = entry.offset
            if source.resolve().parent != self.path.parent.resolve():
                raise VpkError("VPK chunk resolves outside its archive directory")
        with _regular_file(source) as stream:
            if offset + entry.length > os.fstat(stream.fileno()).st_size:
                raise VpkError(f"Entry exceeds its archive chunk: {entry.path}")
            stream.seek(offset)
            payload = entry.preload + _read_exact(stream, entry.length)
        if zlib.crc32(payload) != entry.crc32:
            raise VpkError(f"CRC32 mismatch: {entry.path}")
        return payload


def inventory(vpk: Vpk, extensions: list[str], prefix: str, limit: int, contains: str = "") -> dict:
    wanted = {ext.lower().lstrip(".") for ext in extensions}
    selected = [entry for entry in vpk.entries.values()
                if (not wanted or entry.path.rsplit(".", 1)[-1].lower() in wanted)
                and entry.path.casefold().startswith(prefix.casefold())
                and contains.casefold() in entry.path.casefold()]
    selected.sort(key=lambda entry: entry.path)
    counts = Counter(Path(entry.path).suffix.lstrip(".") or "(none)" for entry in vpk.entries.values())
    return {"format": "source2-vpk-reference-inventory", "version": 1, "archive": vpk.provenance(),
            "payloadsVerified": False,
            "extensionCounts": dict(sorted(counts.items())),
            "filter": {"extensions": sorted(wanted), "prefix": prefix, "contains": contains},
            "matchedEntries": len(selected), "listedEntries": min(limit, len(selected)),
            "truncated": len(selected) > limit,
            "entries": [entry.metadata() for entry in selected[:limit]]}


def extract(vpk: Vpk, names: list[str], output: Path) -> dict:
    if not 1 <= len(names) <= MAX_EXTRACT_ENTRIES:
        raise VpkError("Select between 1 and 64 exact entries per extraction")
    entries = [vpk.find(name) for name in names]
    if len({entry.path.casefold() for entry in entries}) != len(entries):
        raise VpkError("The extraction selection contains duplicate entries")
    paths = {entry.path.casefold() for entry in entries}
    if any(entry.path.split("/", 1)[0].casefold() == "vpk-reference-manifest.json" for entry in entries) or any(
        "/".join(entry.path.casefold().split("/")[:index]) in paths
        for entry in entries for index in range(1, len(entry.path.split("/")))
    ):
        raise VpkError("Selected entries collide with a directory or the extraction manifest")
    if sum(entry.length + len(entry.preload) for entry in entries) > MAX_TOTAL_BYTES:
        raise VpkError("Extraction exceeds the 256 MiB total limit")
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise VpkError("Output must be a new directory with an existing parent; existing outputs are never overwritten")
    for ancestor in (output.parent, *output.parent.parents):
        if _is_link(ancestor.lstat()):
            raise VpkError("Output ancestors cannot be symlinks or reparse points")
    if output.resolve().is_relative_to(vpk.path.parent.resolve()):
        raise VpkError("Use a work directory outside the source archive directory")
    # Verify every selected payload before creating any output directory.
    payloads = [(entry, vpk.read(entry)) for entry in entries]
    manifest = {"format": "source2-vpk-reference-extraction", "version": 1,
                "archive": vpk.provenance(), "entries": [
                    {**entry.metadata(), "sha256": hashlib.sha256(data).hexdigest(), "crc32Verified": True}
                    for entry, data in payloads]}
    output.mkdir()
    for entry, data in payloads:
        destination = output.joinpath(*entry.path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
    with (output / "vpk-reference-manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("inventory", help="Read the bounded directory index; write JSON to stdout")
    listing.add_argument("--vpk", required=True, type=Path)
    listing.add_argument("--extension", action="append", default=[], help="Repeat to select several extensions")
    listing.add_argument("--prefix", default="", help="Case-insensitive archive path prefix")
    listing.add_argument("--contains", default="", help="Case-insensitive literal substring anywhere in the archive path")
    listing.add_argument("--limit", type=int, default=20, help="Number of listed entries, 0..1000; counts always cover the index")
    extracting = commands.add_parser("extract", help="Extract exact entries and a provenance manifest into a new work directory")
    extracting.add_argument("--vpk", required=True, type=Path)
    extracting.add_argument("--entry", action="append", required=True, help="Exact indexed path; repeat up to 64 times")
    extracting.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory" and not 0 <= args.limit <= 1000:
            raise VpkError("--limit must be between 0 and 1000")
        vpk = Vpk(args.vpk)
        report = inventory(vpk, args.extension, args.prefix, args.limit, args.contains) if args.command == "inventory" else extract(vpk, args.entry, args.output)
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except (OSError, VpkError) as exc:
        print(f"vpk_reference: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
