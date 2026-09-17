#!/usr/bin/env python3
"""Compile a TeX manuscript and render its pages; visual inspection remains human/model work."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import re
from pathlib import Path
from audit_core import inside, sha
from package_overleaf import source_tree_digest


def run(command: list[str], cwd: Path, env=None) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)


def locate(binary: str) -> str | None:
    variable = "HUAWEI_POPPLER_BIN" if binary == "pdftoppm" else "HUAWEI_MIKTEX_BIN"
    configured = os.environ.get(variable)
    if configured:
        candidate = Path(configured) / (f"{binary}.exe" if os.name == "nt" else binary)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(binary)


def compile_bibliography(source: Path, output: Path, miktex: bool = False) -> str | None:
    """Resolve the bibliography declared by the fresh TeX auxiliary files."""
    bcf = output / f"{source.stem}.bcf"
    aux = output / f"{source.stem}.aux"
    if bcf.is_file():
        backend = "biber"
        args = ["--input-directory", str(output), "--output-directory", str(output), source.stem]
    elif aux.is_file() and re.search(r"\\bibdata\{", aux.read_text(encoding="utf-8", errors="replace")):
        backend = "bibtex"
        args = (["--enable-installer=no"] if miktex else []) + [source.stem]
    else:
        return None
    tool = locate(backend)
    if not tool:
        print(f"render blocked: {backend} is required by this manuscript", flush=True)
        raise SystemExit(2)
    # BibTeX writes beside the aux file. Search source-local .bib/.bst files as
    # well as the TeX installation defaults, without copying them into QA.
    env = os.environ.copy()
    for key in ("BIBINPUTS", "BSTINPUTS"):
        env[key] = str(source.parent) + os.pathsep + env.get(key, "")
    run([tool, *args], source.parent if backend == "biber" else output, env=env)
    return backend


def proof_draft(project: Path, source: Path, pdf: Path, pages: list[Path], dpi: int) -> dict:
    page_paths = [path.relative_to(project).as_posix() for path in pages]
    pdf_path = pdf.relative_to(project).as_posix()
    return {
        "source_path": source.relative_to(project).as_posix(),
        "source_sha256": sha(source),
        "source_tree_sha256": source_tree_digest(source.parent),
        "rendered_path": pdf_path,
        "rendered_sha256": sha(pdf),
        "rendered_pdf": pdf_path,
        "rendered_pdf_sha256": sha(pdf),
        "render_binding": {"engine": "pdftoppm", "dpi": dpi, "pdf_sha256": sha(pdf)},
        "page_images": page_paths,
        "page_sha256": {path: sha(project / path) for path in page_paths},
        "page_count": len(page_paths),
        "visual_inspection": {
            "typography_and_hierarchy": "pending",
            "math_and_cjk_glyphs": "pending",
            "tables_figures_captions": "pending",
            "layout_and_readability": "pending",
            "evidence_labels_and_references": "pending",
            "defects": ["visual inspection not completed"],
        },
        "cycles": [],
        "passed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--source", required=True, help="project-relative .tex file")
    parser.add_argument("--output-dir", required=True, help="project-relative render directory")
    parser.add_argument("--passes", type=int, default=2, help="compile passes to resolve references")
    args = parser.parse_args()
    project = args.project.resolve()
    source = inside(project, args.source)
    output = inside(project, args.output_dir)
    if output == project:
        parser.error('use a dedicated render directory, not the project root')
    if output.is_relative_to(source.parent):
        parser.error('render output must be outside the authoritative LaTeX source directory')
    xelatex = locate("xelatex")
    pdftoppm = locate("pdftoppm")
    if not xelatex or not pdftoppm:
        print("render blocked: xelatex and pdftoppm are both required", flush=True)
        return 2
    if not source.is_file() or source.suffix.lower() != ".tex":
        print("render blocked: --source must be an existing .tex file", flush=True)
        return 2
    output.mkdir(parents=True, exist_ok=True)
    # Remove only renderer-owned page images so a shorter rerender cannot
    # inherit stale pages from an earlier, longer manuscript.
    for stale in output.glob("page-*.png"):
        stale.unlink()
    # A prior biber/BibTeX run must not choose the backend after the manuscript
    # switched to another bibliography system (or removed it entirely).
    for suffix in (".bcf", ".bbl", ".blg", ".aux", ".run.xml"):
        stale = output / f"{source.stem}{suffix}"
        if stale.is_file():
            stale.unlink()
    version = subprocess.run([xelatex,'--version'],capture_output=True,text=True,errors='replace').stdout
    extra = ['--enable-installer=no'] if 'miktex' in version.lower() else []
    compile_passes = max(2, args.passes)
    bibliography_backend = None
    for pass_index in range(compile_passes):
        run([xelatex, *extra, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "-output-directory", str(output), source.name], source.parent)
        if pass_index == 0:
            bibliography_backend = compile_bibliography(source, output, bool(extra))
    if bibliography_backend:
        # First pass discovers citations; two TeX passes after the bibliography
        # stabilize labels and cross-references in the final PDF.
        run([xelatex, *extra, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", "-output-directory", str(output), source.name], source.parent)
        compile_passes += 1
    pdf = output / f"{source.stem}.pdf"
    if not pdf.exists():
        print("render blocked: compiler produced no PDF", flush=True)
        return 3
    log=(output/f'{source.stem}.log').read_text(encoding='utf-8',errors='replace')
    critical=[line for line in log.splitlines() if re.search(r'Missing character:|There were undefined references|(?:Reference|Citation).*undefined',line)]
    layout_warnings=[line for line in log.splitlines() if re.search(r'(?:Over|Under)full \\[hv]box',line)]
    if critical:
        print(json.dumps({'render_blocked':critical},ensure_ascii=False));return 3
    dpi = 150
    prefix = output / "page"
    run([pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)], project)
    pages = sorted(output.glob('page-*.png'), key=lambda p:int(re.search(r'(\d+)\.png$',p.name)[1]))
    manifest = proof_draft(project, source, pdf, pages, dpi)
    manifest.update(render_engine="xelatex + pdftoppm",compile_passes=compile_passes,
                    bibliography_backend=bibliography_backend,compile_warnings=layout_warnings)
    (output / "render-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS render draft: {len(pages)} pages; visual inspection pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
