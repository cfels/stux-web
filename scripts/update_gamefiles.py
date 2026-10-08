"""Import a SuperTux WASM ZIP, tar archive, or extracted release folder."""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAME = REPO / "SuperTux-v0.6.3-WASM"
CHUNK_SIZE = 32 * 1024 * 1024


def unpack(source, destination):
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise ValueError(f"Unsafe archive path: {member.filename}")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Archive symlinks are not supported: {member.filename}")
            archive.extractall(destination)
    elif tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            for member in archive.getmembers():
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"Unsupported archive entry: {member.name}")
            archive.extractall(destination, filter="data")
    else:
        raise ValueError("Use a ZIP, tar/tar.gz archive, or an extracted folder.")


def replace_once(pattern, replacement, text, label):
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f"Expected one {label}, found {count}.")
    return updated


def prepare(source, staged):
    candidates = list(source.rglob("supertux2.data"))
    if len(candidates) != 1:
        raise ValueError(f"Expected one supertux2.data file, found {len(candidates)}.")
    release = candidates[0].parent
    for name in ("supertux2.html", "supertux2.js", "supertux2.wasm"):
        if not (release / name).is_file():
            raise ValueError(f"Release is missing {name}.")
    for path in release.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Release symlinks are not supported: {path}")
        if not path.is_file() or path.name == "supertux2.data" or path.name.startswith("supertux2.data.part") or path.name == "start.js":
            continue
        target = staged / path.relative_to(release)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    digest = hashlib.sha256()
    size = 0
    count = 0
    with candidates[0].open("rb") as original:
        while chunk := original.read(CHUNK_SIZE):
            (staged / f"supertux2.data.part{count}").write_bytes(chunk)
            digest.update(chunk)
            size += len(chunk)
            count += 1
    if not size:
        raise ValueError("Game data is empty.")
    # Verify bytes read back from the split files before replacing any game assets.
    joined = hashlib.sha256()
    for part in range(count):
        with (staged / f"supertux2.data.part{part}").open("rb") as stream:
            while block := stream.read(1024 * 1024):
                joined.update(block)
    if joined.digest() != digest.digest():
        raise ValueError("Split data does not match the original archive.")

    loader = (GAME / "start.js").read_text(encoding="utf-8")
    loader = replace_once(r"new Uint8Array\(\d+\)", f"new Uint8Array({size})", loader, "loader data size")
    loader = replace_once(r"part < \d+", f"part < {count}", loader, "loader part count")
    (staged / "start.js").write_text(loader, encoding="utf-8")

    html_path = staged / "supertux2.html"
    html = html_path.read_text(encoding="utf-8")
    # Keep Module initialization from the release, but load the split-data bootstrap.
    script_pattern = r"<script\b[^>]*\bsrc\s*=\s*[\"'](?:\./)?(?:supertux2|start)\.js[\"'][^>]*>\s*</script\s*>"
    html = replace_once(script_pattern, '<script src="start.js"></script>', html, "game script tag")
    html_path.write_text(html, encoding="utf-8")

    verifier_path = REPO / "scripts" / "verify_game_data.py"
    verifier = verifier_path.read_text(encoding="utf-8")
    verifier = replace_once(r"EXPECTED_SIZE = \d+", f"EXPECTED_SIZE = {size}", verifier, "verification data size")
    verifier = replace_once(r'EXPECTED_SHA256 = "[0-9a-f]+"', f'EXPECTED_SHA256 = "{digest.hexdigest()}"', verifier, "verification hash")
    staged_verifier = staged.parent / "verify_game_data.py"
    staged_verifier.write_text(verifier, encoding="utf-8")
    subprocess.run([sys.executable, str(staged_verifier), "--directory", str(staged)], check=True)
    return verifier_path, verifier, candidates[0], count, size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to a release ZIP/tar archive or extracted folder")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.exists():
        parser.error(f"Source does not exist: {source}")
    with tempfile.TemporaryDirectory(prefix="stux-import-") as temp:
        temporary = Path(temp)
        if source.is_dir():
            extracted = source
        else:
            extracted = temporary / "extracted"
            extracted.mkdir()
            unpack(source, extracted)
        staged = temporary / "game"
        staged.mkdir()
        verifier_path, verifier, original, count, size = prepare(extracted, staged)
        GAME.mkdir(parents=True, exist_ok=True)
        for path in staged.rglob("*"):
            if path.is_file():
                target = GAME / path.relative_to(staged)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        # Only remove obsolete generated chunks inside the fixed game directory.
        expected = {f"supertux2.data.part{part}" for part in range(count)}
        for path in GAME.glob("supertux2.data.part*"):
            if path.is_file() and path.name not in expected:
                path.unlink()
        local_original = GAME / "supertux2.data"
        if local_original.exists() and local_original.resolve() != original.resolve():
            local_original.unlink()
        verifier_path.write_text(verifier, encoding="utf-8")
        subprocess.run([sys.executable, str(verifier_path), "--directory", str(GAME)], check=True)
        print(f"Imported {size:,} bytes in {count} parts (maximum 32 MiB each).")
        print("Loader and verification values updated. Review, commit, and push the changes.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise SystemExit(f"Import failed: {error}")
