#!/usr/bin/env python3
"""Probe the formal manuscript toolchain without third-party packages."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def locate(binary: str) -> str | None:
    # Only the TeX binaries honor HUAWEI_MIKTEX_BIN and only Poppler tools
    # honor HUAWEI_POPPLER_BIN; everything else resolves via PATH.
    variable = {"pdftoppm": "HUAWEI_POPPLER_BIN", "pdftotext": "HUAWEI_POPPLER_BIN",
                "xelatex": "HUAWEI_MIKTEX_BIN", "kpsewhich": "HUAWEI_MIKTEX_BIN"}.get(binary)
    configured = os.environ.get(variable) if variable else None
    if configured:
        candidate = Path(configured) / (f"{binary}.exe" if os.name == "nt" else binary)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(binary)


def version(binary: str) -> str | None:
    path = locate(binary)
    if not path:
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        if result.returncode and binary in {"pdftoppm", "pdftotext"}:
            result = subprocess.run([path, "-v"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return path
    first = (result.stdout or result.stderr).splitlines()
    return first[0].strip() if first else path


def probe_ctex() -> str | None:
    kpsewhich = locate("kpsewhich") or shutil.which("kpsewhich")
    if kpsewhich:
        try:
            result = subprocess.run([kpsewhich, "ctexart.cls"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            found = (result.stdout or "").strip()
            if result.returncode == 0 and found:
                return found
        except (OSError, subprocess.SubprocessError):
            pass
    miktex_bin = os.environ.get("HUAWEI_MIKTEX_BIN")
    if miktex_bin:
        base = Path(miktex_bin)
        candidates = [
            base.parent / "tex" / "latex" / "ctex" / "ctexart.cls",
            base.parents[2] / "tex" / "latex" / "ctex" / "ctexart.cls" if len(base.parents) > 2 else base / "missing",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def probe_cjk_fonts() -> list[str]:
    fc_list = locate("fc-list")
    if not fc_list:
        return []
    try:
        result = subprocess.run([fc_list, ":lang=zh", "family"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        values = []
        for line in (result.stdout or "").splitlines():
            name = line.strip().split(",", 1)[0]
            if name and name not in values:
                values.append(name)
        return values[:20]
    except (OSError, subprocess.SubprocessError):
        return []


def probe_render_env() -> dict:
    """Minimal render environment metadata for reproducible LaTeX/PDF QA."""
    import locale
    import warnings
    env = {
        "locale": locale.getlocale(),
        "preferred_encoding": locale.getpreferredencoding(False),
        "python": platform.python_version(),
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            env["default_locale"] = locale.getdefaultlocale()
        except ValueError:
            env["default_locale"] = None
    fonts = probe_cjk_fonts()
    env["cjk_fonts"] = fonts
    env['font_probe_available']=bool(fonts)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-xelatex", action="store_true")
    args = parser.parse_args()
    tools = {name: version(name) for name in ("xelatex", "pdftoppm", "pdftotext", "fc-list", "kpsewhich")}
    ctex_path = probe_ctex()
    cjk_fonts = probe_cjk_fonts()
    report = {
        "platform": platform.platform(),
        "tools": tools,
        "ctex_available": bool(ctex_path),
        "ctex_path": ctex_path,
        "cjk_fonts": cjk_fonts,
        "pdf_route_ready": bool(tools["xelatex"] and tools["pdftoppm"]),
        "readiness_scope": "renderer availability only; ctex/font findings are informative and the actual current manuscript compile is authoritative",
        "font_probe_available": bool(tools["fc-list"]),
        "render_env": probe_render_env(),
    }
    report['packaging_capabilities']={'zip':True,'overleaf_zip':True}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.require_xelatex and not report["pdf_route_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
