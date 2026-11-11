"""The build-time downloader keeps what the editor loads and drops the rest."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "docker" / "fetch_editor_assets.py"
spec = importlib.util.spec_from_file_location("fetch_editor_assets", SCRIPT)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def test_monaco_keeps_the_html_editor_and_drops_other_language_services():
    keep = fetch.wanted
    assert keep("monaco-editor", "min/vs/loader.js")
    assert keep("monaco-editor", "min/vs/language/html/htmlMode.js")
    assert not keep("monaco-editor", "min/vs/language/typescript/tsMode.js")
    assert not keep("monaco-editor", "esm/vs/editor/editor.main.js")


def test_tinymce_keeps_min_files_of_the_used_plugins_only():
    keep = fetch.wanted
    assert keep("tinymce", "tinymce.min.js")
    assert keep("tinymce", "plugins/link/plugin.min.js")
    assert keep("tinymce", "plugins/table/plugin.min.js")  # tables in signatures
    assert keep("tinymce", "skins/ui/oxide-dark/skin.min.css")
    assert not keep("tinymce", "plugins/emoticons/plugin.min.js")
    assert not keep("tinymce", "plugins/link/plugin.js")
    assert not keep("tinymce", "tinymce.js")
