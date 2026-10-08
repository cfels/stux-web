"""Verify split game data before and after the Pages build."""
import argparse
import hashlib
from pathlib import Path

EXPECTED_SIZE = 245929603
EXPECTED_SHA256 = "bb0b48c62eeb357457c0dbcd869ef559795e5d55691c04d46d51dde60f1d0f2e"
CHUNK_SIZE = 32 * 1024 * 1024
PART_COUNT = (EXPECTED_SIZE + CHUNK_SIZE - 1) // CHUNK_SIZE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("SuperTux-v0.6.3-WASM"))
    directory = parser.parse_args().directory
    expected_names = {f"supertux2.data.part{part}" for part in range(PART_COUNT)}
    actual_names = {path.name for path in directory.glob("supertux2.data.part*")}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise SystemExit(
            f"Chunk files in {directory}: missing={missing}, unexpected={unexpected}"
        )

    digest = hashlib.sha256()
    total = 0
    for part in range(PART_COUNT):
        path = directory / f"supertux2.data.part{part}"
        expected_part_size = min(CHUNK_SIZE, EXPECTED_SIZE - part * CHUNK_SIZE)
        if path.stat().st_size != expected_part_size:
            raise SystemExit(f"{path}: expected {expected_part_size} bytes, got {path.stat().st_size}")
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
                total += len(block)
        print(f"{path.name}: {path.stat().st_size:,} bytes")

    if total != EXPECTED_SIZE or digest.hexdigest() != EXPECTED_SHA256:
        raise SystemExit("Split data does not match the original game's size and SHA-256.")

    original = directory / "supertux2.data"
    if original.exists():
        with original.open("rb") as stream:
            original_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if original.stat().st_size != total or original_hash != digest.hexdigest():
            raise SystemExit("Local original file differs from the reconstructed chunks.")
        print("Local original file matches the chunks byte for byte (SHA-256).")

    loader = (directory / "start.js").read_text(encoding="utf-8")
    if f"new Uint8Array({EXPECTED_SIZE})" not in loader or f"part < {PART_COUNT}" not in loader:
        raise SystemExit("Loader size or chunk count does not match the verified data.")
    print(f"Verified {PART_COUNT} parts: {total:,} bytes, SHA-256 {digest.hexdigest()}")


if __name__ == "__main__":
    main()
