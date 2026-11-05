"""Download the pinned Monaco and TinyMCE builds from the npm registry.

Run at image build time (see the ``assets`` stage in the Dockerfile) so the
template editor works without reaching a CDN. Usage::

    python fetch_editor_assets.py <target-dir>

Tarballs are verified against the registry's sha512 integrity value, so a
version bump means updating the version *and* the hash below (``npm view
<package>@<version> dist.integrity``). Keep the versions in sync with
``template_editor.js``, whose CDN fallback uses the same ones.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import PurePosixPath

# name, version, sha512 (base64), target folder
PACKAGES = [
    (
        "monaco-editor",
        "0.50.0",
        "8CclLCmrRRh+sul7C08BmPBP3P8wVWfBHomsTcndxg5NRCEPfu/mc2AGU8k37ajjDVXcXFc12ORAMUkmk+lkFA==",
        "monaco-editor",
    ),
    (
        "tinymce",
        "7.3.0",
        "Ls4PgYlpk73XAxBSBqbVmSl8Mb3DuNfgF01GZ0lY6/MOEVRl3IL+VxC1Oe6165e8WqbqVsxO3Qj/PmoYNvQKGQ==",
        "tinymce",
    ),
]

# The editor only uses HTML and plain text; the TypeScript, CSS and JSON
# language services alone are ~6 MB.
MONACO_SKIP = ("min/vs/language/typescript/", "min/vs/language/css/", "min/vs/language/json/")
TINYMCE_KEEP = (
    "tinymce.min.js",
    "license.txt",
    "skins/",
    "themes/silver/",
    "models/dom/",
    "icons/default/",
    "plugins/link/",
    "plugins/lists/",
    "plugins/code/",
)


def wanted(package: str, path: str) -> bool:
    """Whether ``path`` (relative to the package root) belongs in the image."""
    if package == "monaco-editor":
        return path.startswith("min/vs/") and not path.startswith(MONACO_SKIP)
    # TinyMCE loads the ".min" files (``suffix: ".min"``); skip sources and maps.
    if not path.startswith(TINYMCE_KEEP):
        return False
    name = PurePosixPath(path).name
    if name.endswith(".js"):
        return name.endswith(".min.js")
    if name.endswith(".css"):
        return name.endswith(".min.css")
    return not name.endswith((".map", ".ts"))


def fetch(package: str, version: str, integrity: str, folder: str, target: str) -> None:
    url = f"https://registry.npmjs.org/{package}/-/{package}-{version}.tgz"
    data = urllib.request.urlopen(url, timeout=120).read()  # noqa: S310 — fixed https URL
    digest = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if digest != integrity:
        sys.exit(f"{package}@{version}: integrity mismatch (got sha512-{digest})")

    count = 0
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            relative = member.name.split("/", 1)[1]  # strip the leading "package/"
            if not wanted(package, relative):
                continue
            destination = PurePosixPath(target, folder, relative)
            source = tar.extractfile(member)
            assert source is not None

            os.makedirs(destination.parent, exist_ok=True)
            with open(destination, "wb") as out:
                out.write(source.read())
            count += 1
    print(f"{package}@{version}: {count} files")


if __name__ == "__main__":
    for package, version, integrity, folder in PACKAGES:
        fetch(package, version, integrity, folder, sys.argv[1])
