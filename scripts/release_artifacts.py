#!/usr/bin/env python3
"""Create checksums and an SPDX SBOM for a standalone Windows build."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path


_LOCKED_PACKAGE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.!+-]+)\s+--hash=sha256:[0-9a-f]{64}$")


def parse_locked_packages(requirements_path: Path) -> list[tuple[str, str]]:
    """Read exact package versions from the reviewed Windows lock file."""

    packages: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(requirements_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LOCKED_PACKAGE.fullmatch(line)
        if match is None:
            raise ValueError(f"Invalid locked requirement at {requirements_path.name}:{line_number}")
        packages.append((match.group(1), match.group(2)))
    if not packages:
        raise ValueError(f"No locked packages found in {requirements_path}")
    return packages


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_release_files(artifact_root: Path, metadata_dir: Path) -> list[Path]:
    """List deliverable files, excluding generated metadata itself."""

    root = artifact_root.resolve()
    excluded = metadata_dir.resolve()
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and not path.resolve().is_relative_to(excluded)),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def installed_locked_packages(packages: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Confirm the SBOM reflects the exact dependency lock, not ambient packages."""

    resolved: list[dict[str, str]] = []
    for package_name, expected_version in packages:
        try:
            distribution = metadata.distribution(package_name)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Locked package is not installed: {package_name}") from exc
        if distribution.version != expected_version:
            raise RuntimeError(
                f"Installed {package_name} version {distribution.version} does not match lock {expected_version}"
            )
        resolved.append(
            {
                "name": distribution.metadata.get("Name", package_name),
                "version": distribution.version,
                "license": distribution.metadata.get("License-Expression")
                or distribution.metadata.get("License")
                or "NOASSERTION",
            }
        )
    return resolved


def write_release_metadata(
    artifact_root: Path,
    metadata_dir: Path,
    packages: list[dict[str, str]],
) -> tuple[Path, Path]:
    """Write checksum and SPDX documents for files already present in ``artifact_root``."""

    root = artifact_root.resolve()
    output = metadata_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = collect_release_files(root, output)
    if not files:
        raise RuntimeError(f"No release artifacts found under {root}")

    checksums_path = output / "SHA256SUMS.txt"
    checksum_lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in files]
    checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    spdx_files = [
        {
            "SPDXID": f"SPDXRef-File-{index}",
            "fileName": path.relative_to(root).as_posix(),
            "checksums": [{"algorithm": "SHA256", "checksumValue": sha256_file(path)}],
            "licenseConcluded": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        }
        for index, path in enumerate(files, start=1)
    ]
    spdx_packages = [
        {
            "SPDXID": f"SPDXRef-Package-{index}",
            "name": package["name"],
            "versionInfo": package["version"],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": package["license"],
            "licenseDeclared": package["license"],
            "copyrightText": "NOASSERTION",
        }
        for index, package in enumerate(packages, start=1)
    ]
    relationships = [
        {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": item["SPDXID"]}
        for item in (*spdx_files, *spdx_packages)
    ]
    sbom_path = output / "sbom.spdx.json"
    sbom_path.write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "BlastFromTheAds-release",
                "documentNamespace": "https://github.com/wizkidword/blast-from-the-ads-poster/releases/local-build",
                "creationInfo": {
                    "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "creators": ["Tool: Blast From the Ads release_artifacts.py"],
                },
                "packages": spdx_packages,
                "files": spdx_files,
                "relationships": relationships,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return checksums_path, sbom_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write release checksums and an SPDX SBOM")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    packages = installed_locked_packages(parse_locked_packages(args.requirements))
    checksums_path, sbom_path = write_release_metadata(args.artifact_root, args.output_dir, packages)
    print(f"Wrote checksums: {checksums_path}")
    print(f"Wrote SBOM: {sbom_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
