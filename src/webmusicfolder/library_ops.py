"""Blocking file operations behind the Library: delete, move and subfolder management."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from webmusicfolder.library import MP3_SUFFIX
from webmusicfolder.paths import PathError, resolve_inside, validate_subfolder


@dataclass
class BatchResult:
    # Relative paths that were handled, plus (path, reason) for those that were not.
    done: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    # old relpath -> new relpath, filled by moves
    moved: dict[str, str] = field(default_factory=dict)


def mp3_path(music_dir: Path, relpath: str) -> Path:
    """Resolve a library relpath to an existing MP3 inside the music dir or raise PathError."""
    if not relpath.lower().endswith(MP3_SUFFIX) or "\x00" in relpath:
        raise PathError("not an mp3 file")
    parts = relpath.split("/")
    if any(p.startswith(".") or p == "" for p in parts):
        raise PathError("invalid path")
    target = resolve_inside(music_dir, *parts)
    if not target.is_file():
        raise PathError("file not found")
    return target


def delete_files(music_dir: Path, relpaths: list[str]) -> BatchResult:
    result = BatchResult()
    for rel in relpaths:
        try:
            mp3_path(music_dir, rel).unlink()
            result.done.append(rel)
        except PathError as exc:
            result.failed.append((rel, str(exc)))
        except OSError as exc:
            result.failed.append((rel, f"could not delete: {exc.strerror or exc}"))
    return result


def move_files(music_dir: Path, relpaths: list[str], subfolder: str) -> BatchResult:
    """Move MP3s into a first level subfolder ('' for the music root), never overwriting."""
    name = validate_subfolder(subfolder)
    result = BatchResult()
    dest_dir = resolve_inside(music_dir, name) if name else resolve_inside(music_dir)
    root = resolve_inside(music_dir)
    for rel in relpaths:
        try:
            source = mp3_path(music_dir, rel)
            dest_dir.mkdir(parents=True, exist_ok=True)
            target = dest_dir / source.name
            if target == source:
                result.failed.append((rel, "already in that folder"))
                continue
            if target.exists():
                result.failed.append((rel, "a file with that name already exists there"))
                continue
            shutil.move(str(source), str(target))
            new_rel = target.relative_to(root).as_posix()
            result.done.append(rel)
            result.moved[rel] = new_rel
        except PathError as exc:
            result.failed.append((rel, str(exc)))
        except OSError as exc:
            result.failed.append((rel, f"could not move: {exc.strerror or exc}"))
    return result


def _folder_path(music_dir: Path, name: str) -> Path:
    clean = validate_subfolder(name)
    if not clean or clean.startswith("."):
        raise PathError("invalid folder name")
    raw = Path(music_dir, clean)
    if raw.is_symlink():
        raise PathError("folder not found")
    return resolve_inside(music_dir, clean)


def create_folder(music_dir: Path, name: str) -> str:
    path = _folder_path(music_dir, name)
    path.mkdir(parents=True, exist_ok=True)
    return path.name


def delete_folder(music_dir: Path, name: str) -> int:
    """Remove a first level subfolder with everything in it; returns the MP3 count removed."""
    path = _folder_path(music_dir, name)
    if not path.is_dir():
        raise PathError("folder not found")
    count = sum(1 for p in path.rglob("*") if p.is_file() and p.suffix.lower() == MP3_SUFFIX)
    shutil.rmtree(path)
    return count
