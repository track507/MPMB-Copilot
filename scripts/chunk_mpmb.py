"""
MPMB Source Code Chunker - CLI Entrypoint

Run from project root:
    python scripts/chunk_mpmb.py

All configuration comes from .env via app.config.config.
Override with environment variables:
    MPMB_SOURCE_DIR=./my/mpmb python scripts/chunk_mpmb.py
"""

import sys
import logging
from pathlib import Path

# Add backend/ to path so we can import app modules
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from app.config import config
    from app.core.chunker import MPMBChunker

    print("=" * 70)
    print("MPMB SOURCE CODE CHUNKER")
    print("=" * 70)

    source_configs = config.source_configs
    output_dir = config.chunked_output_path

    print(f"\nOutput: {output_dir}")
    print(f"Sources ({len(source_configs)}):")
    for cfg in source_configs:
        print(f"  [{cfg['edition']:>7s}] {cfg['path']}  ({cfg['description']})")

    if not source_configs:
        print("\nNo source directories found. Clone the repos first:")
        print(f"  git clone {config.mpmb_repo_url} {config.mpmb_source_dir}")
        print(
            f"  git clone --branch {config.mpmb_repo_branch_2024} "
            f"{config.mpmb_repo_url} {config.mpmb_source_2024_dir}"
        )
        print(f"  git clone {config.imports_repo_url} {config.imports_source_dir}")
        return 1

    chunker = MPMBChunker()
    result = chunker.run_all(source_configs=source_configs, output_dir=output_dir)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(chunker.get_stats_summary())
    print("=" * 70)

    if result.get("output_files"):
        print(f"\nOutput files ({len(result['output_files'])}):")
        for fname in result["output_files"]:
            fpath = output_dir / fname
            size_kb = fpath.stat().st_size / 1024 if fpath.exists() else 0
            print(f"  {fname}: {size_kb:.1f} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
