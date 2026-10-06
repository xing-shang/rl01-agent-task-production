#!/usr/bin/env python3
"""Read-only static preflight of the actual final RL0-1 batch ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from check_rl01_package import ENGINEERING_VERSION, validate
from check_rl01_evidence import audit_evidence, build_manifest, compare_manifest, strict_json


GLOBAL_RESIDUE = {".DS_Store", "__MACOSX", ".git", "__pycache__", ".venv"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def member_name(info: zipfile.ZipInfo) -> str:
    # Some existing macOS ZIPs store UTF-8 bytes without setting bit 11.
    # Decode those bytes rather than extracting mojibake paths. Truly non-UTF-8
    # member names do not meet the delivery filename rule.
    if info.flag_bits & 0x800 or info.filename.isascii():
        return info.filename
    return info.filename.encode("cp437").decode("utf-8")


def check_archive(archive: Path, expected_manifest: Path | None = None) -> dict:
    archive = archive.resolve()
    issues: list[dict] = []
    result = {
        "ok": False,
        "scope": "final_zip_static_preflight_only",
        "engineering_version": ENGINEERING_VERSION,
        "archive": str(archive),
        "archive_sha256": None,
        "checker_sha256": sha256(Path(__file__).resolve()),
        "task_checker_sha256": sha256(Path(__file__).with_name("check_rl01_package.py")),
        "issues": issues,
        "tasks": [],
        "evidence": None,
        "staging_manifest_checked": expected_manifest is not None,
    }

    def fail(rule: str, detail: str) -> None:
        issues.append({"rule": rule, "detail": detail})

    if not archive.is_file():
        fail("archive", "ZIP file does not exist")
        return result
    result["archive_sha256"] = sha256(archive)
    try:
        with zipfile.ZipFile(archive) as source:
            members: list[tuple[zipfile.ZipInfo, str]] = []
            seen: set[str] = set()
            unsafe = False
            for info in source.infolist():
                try:
                    name = member_name(info)
                except (UnicodeError, ValueError):
                    fail("archive-filename", "member filename is not valid UTF-8")
                    unsafe = True
                    continue
                path = PurePosixPath(name)
                if (not path.parts or path.is_absolute() or ".." in path.parts
                        or "\\" in name or ":" in path.parts[0]
                        or name.rstrip("/") != path.as_posix()):
                    fail("archive-path", f"invalid member path: {name}")
                    unsafe = True
                    continue
                if path.as_posix() in seen:
                    fail("archive-path", f"duplicate member path: {name}")
                    unsafe = True
                seen.add(path.as_posix())
                if stat.S_ISLNK(info.external_attr >> 16):
                    fail("archive-path", f"symlink member: {name}")
                    unsafe = True
                if GLOBAL_RESIDUE.intersection(path.parts):
                    fail("archive-residue", f"forbidden path anywhere in ZIP: {name}")
                members.append((info, name))
            if unsafe:
                return result
            bad_member = source.testzip()
            if bad_member:
                fail("archive-crc", f"CRC check failed: {bad_member}")
                return result
            roots = {
                PurePosixPath(name).parts[0] for _, name in members
                if not GLOBAL_RESIDUE.intersection(PurePosixPath(name).parts)
            }
            if len(roots) != 1:
                fail("archive-layout", "ZIP must contain one batch root directory")
                return result
            batch = next(iter(roots))
            if f"{batch}/交付文档.md" not in seen:
                fail("archive-layout", "batch root is missing 交付文档.md")
            task_dirs = sorted({
                PurePosixPath(name).parent.as_posix()
                for _, name in members
                if len(PurePosixPath(name).parts) == 3
                and PurePosixPath(name).parts[0] == batch
                and PurePosixPath(name).name == "task.toml"
            })
            if not task_dirs:
                fail("archive-layout", "no task directory directly beneath the batch root")
            with tempfile.TemporaryDirectory(prefix="rl01-final-zip-check-") as temporary:
                extraction = Path(temporary)
                for info, name in members:
                    target = extraction.joinpath(*PurePosixPath(name).parts)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with source.open(info) as stream, target.open("wb") as output:
                            shutil.copyfileobj(stream, output)
                        mode = (info.external_attr >> 16) & 0o777
                        if mode:
                            target.chmod(mode)
                for relative in task_dirs:
                    task_issues, warnings = validate(extraction / relative)
                    result["tasks"].append({
                        "path": relative,
                        "ok": not task_issues,
                        "issues": task_issues,
                        "warnings": warnings,
                    })
                extracted_batch = extraction / batch
                if expected_manifest is not None:
                    try:
                        issues.extend(compare_manifest(extracted_batch, strict_json(expected_manifest)))
                    except (OSError, UnicodeError, ValueError) as error:
                        fail("archive-manifest", str(error))
                result["evidence"] = audit_evidence(extracted_batch)
                issues.extend(result["evidence"]["issues"])
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        fail("archive-read", str(error))
    try:
        if result["archive_sha256"] != sha256(archive):
            fail("archive-changed", "ZIP bytes changed during this check; rerun on the final file")
    except OSError:
        fail("archive-changed", "ZIP became unreadable during this check")
    result["ok"] = not issues and bool(result["tasks"]) and all(task["ok"] for task in result["tasks"])
    result["review_required"] = bool(result["evidence"] and result["evidence"]["review_required"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-manifest", type=Path, help="compare against a manifest recorded from the final staging directory")
    parser.add_argument("--write-manifest", type=Path, help="treat the positional path as the staging directory; save its manifest outside that directory")
    args = parser.parse_args()
    if args.write_manifest:
        if args.expected_manifest:
            parser.error("record and compare are separate operations")
        source = args.archive.resolve(strict=True)
        destination = args.write_manifest.resolve()
        if destination.is_relative_to(source):
            parser.error("the staging manifest must be outside the batch directory")
        manifest = build_manifest(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"ok": True, "scope": "local_staging_file_manifest", "path": str(destination), "files": len(manifest["files"])}, ensure_ascii=False))
        return 0
    result = check_archive(args.archive, args.expected_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
