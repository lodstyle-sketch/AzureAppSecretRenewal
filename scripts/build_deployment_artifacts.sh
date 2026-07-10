#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dist_dir="${repo_root}/dist"

mkdir -p "${dist_dir}"
rm -f "${dist_dir}/webapp.zip"

python3 - <<'PY' "${repo_root}" "${dist_dir}/webapp.zip"
import pathlib
import sys
import zipfile

repo_root = pathlib.Path(sys.argv[1])
zip_path = pathlib.Path(sys.argv[2])
include_files = [repo_root / "requirements.txt", repo_root / "pyproject.toml"]
include_dirs = [repo_root / "credential_renewal"]

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for file_path in include_files:
        archive.write(file_path, file_path.relative_to(repo_root))
    for directory in include_dirs:
        for file_path in directory.rglob("*"):
            if file_path.is_file() and "__pycache__" not in file_path.parts:
                archive.write(file_path, file_path.relative_to(repo_root))
PY

python3 - <<'PY' "${repo_root}" "${dist_dir}"
import base64
import csv
import hashlib
import io
import pathlib
import sys
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback for unusual build agents.
    import tomli as tomllib

repo_root = pathlib.Path(sys.argv[1])
dist_dir = pathlib.Path(sys.argv[2])
project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
name = project["name"]
version = project["version"]
normalized_name = name.replace("-", "_")
wheel_name = f"{normalized_name}-{version}-py3-none-any.whl"
dist_info = f"{normalized_name}-{version}.dist-info"
wheel_path = dist_dir / wheel_name

records: list[tuple[str, str, str]] = []


def digest(data: bytes) -> str:
    value = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return f"sha256={value}"


def write_bytes(archive: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    archive.writestr(arcname, data)
    records.append((arcname, digest(data), str(len(data))))


metadata_lines = [
    "Metadata-Version: 2.1",
    f"Name: {name}",
    f"Version: {version}",
    f"Summary: {project.get('description', '')}",
    f"Requires-Python: {project.get('requires-python', '')}",
]
for dependency in project.get("dependencies", []):
    metadata_lines.append(f"Requires-Dist: {dependency}")
metadata = ("\n".join(metadata_lines) + "\n").encode("utf-8")
wheel = b"Wheel-Version: 1.0\nGenerator: build_deployment_artifacts.sh\nRoot-Is-Purelib: true\nTag: py3-none-any\n"

with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for file_path in (repo_root / "credential_renewal").rglob("*"):
        if file_path.is_file() and "__pycache__" not in file_path.parts:
            arcname = str(file_path.relative_to(repo_root))
            data = file_path.read_bytes()
            write_bytes(archive, arcname, data)

    write_bytes(archive, f"{dist_info}/METADATA", metadata)
    write_bytes(archive, f"{dist_info}/WHEEL", wheel)

    record_name = f"{dist_info}/RECORD"
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for row in records:
        writer.writerow(row)
    writer.writerow((record_name, "", ""))
    archive.writestr(record_name, output.getvalue().encode("utf-8"))
PY

echo "Created:"
echo "  ${dist_dir}/webapp.zip"
find "${dist_dir}" -maxdepth 1 -name 'azure_app_credential_renewal-*.whl' -print
