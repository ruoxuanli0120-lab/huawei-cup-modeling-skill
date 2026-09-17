#!/usr/bin/env python3
"""Create an Overleaf-ready ZIP from the authoritative LaTeX source directory.

The packager never rewrites TeX/Bib/style/class files. It only archives them and
verifies that main.tex in the ZIP is byte-identical to the source.
"""
from __future__ import annotations
import argparse, hashlib, json, zipfile, re
from pathlib import Path

EXCLUDE_DIRS={'.git','__pycache__','.idea','.vscode'}
EXCLUDE_SUFFIXES={'.aux','.log','.toc','.out','.synctex.gz','.fls','.fdb_latexmk','.xdv','.pyc'}
EXCLUDE_NAMES={'.DS_Store','Thumbs.db','desktop.ini'}

def inside(root:Path,value:str)->Path:
    root=root.resolve();p=(root/value).resolve()
    if not p.is_relative_to(root):raise ValueError('path escapes project')
    return p

def digest(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def collect(src:Path):
    files=[]
    for f in sorted(src.rglob('*')):
        if not f.is_file() or f.is_symlink():continue
        if f.name in EXCLUDE_NAMES:continue
        rel=f.relative_to(src)
        if any(x in EXCLUDE_DIRS for x in rel.parts):continue
        if any(f.name.endswith(s) for s in EXCLUDE_SUFFIXES):continue
        files.append(f)
    return files


def source_tree_digest(src:Path)->str:
    """Hash exactly the files that would be sent to Overleaf."""
    h=hashlib.sha256()
    for f in collect(src):
        rel=f.relative_to(src).as_posix().encode('utf-8')
        h.update(len(rel).to_bytes(4,'big'));h.update(rel)
        data=f.read_bytes();h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()

def _external_tex_paths(src:Path, files:list[Path])->list[str]:
    """Return literal TeX file references that escape the Overleaf source root.

    This intentionally checks only path-bearing commands and only parent/absolute
    paths. Ordinary child paths such as figures/a.pdf remain untouched.
    """
    problems=[]
    command=re.compile(r"\\(?:input|include|includegraphics|addbibresource|bibliography|bibliographystyle|lstinputlisting|VerbatimInput|includepdf|documentclass|usepackage)(?:\[[^\]]*\])?\{([^{}]+)\}")
    for f in files:
        if f.suffix.lower() not in {'.tex','.sty','.cls','.ltx'}:
            continue
        try:text=f.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:continue
        text=re.sub(r'(?m)(?<!\\)%.*$','',text)
        for raw in command.findall(text):
            for part in raw.split(','):
                ref=part.strip().replace('\\','/')
                if not ref:continue
                pieces=[x for x in ref.split('/') if x not in ('','.')]
                if ref.startswith('/') or re.match(r'^[A-Za-z]:/',ref) or '..' in pieces:
                    problems.append(f"{f.relative_to(src).as_posix()}: external path {part.strip()}")
        # \graphicspath{{figures/}{../shared/}} can hide external image roots.
        for block in re.findall(r'\\graphicspath\{((?:\{[^{}]*\})+)\}', text):
            for raw in re.findall(r'\{([^{}]*)\}', block):
                ref=raw.strip().replace('\\','/')
                pieces=[x for x in ref.split('/') if x not in ('','.')]
                if ref.startswith('/') or re.match(r'^[A-Za-z]:/',ref) or '..' in pieces:
                    problems.append(f"{f.relative_to(src).as_posix()}: external graphicspath {raw.strip()}")
    return problems

def build(project:Path,source_dir:str,main:str,output:str)->dict:
    project=project.resolve();src=inside(project,source_dir);out=inside(project,output)
    if not src.is_dir():raise ValueError('source-dir not found')
    if out.is_relative_to(src):raise ValueError('output ZIP must be outside source-dir so packaging cannot change the authoritative source tree')
    main_path=(src/main).resolve()
    if not main_path.is_relative_to(src) or not main_path.is_file() or main_path.suffix.lower()!='.tex':
        raise ValueError('main must be an existing .tex inside source-dir')
    files=collect(src)
    if main_path not in files:raise ValueError('main.tex excluded unexpectedly')
    external=_external_tex_paths(src,files)
    if external:raise ValueError('Overleaf source must be self-contained; '+ '; '.join(external[:5]))
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files:z.write(f,f.relative_to(src).as_posix())
    with zipfile.ZipFile(out) as z:
        bad=z.testzip();names=z.namelist()
        if bad:raise ValueError('corrupt zip member: '+bad)
        if main not in names:raise ValueError('main file missing from zip')
        zipped=z.read(main)
    source_bytes=main_path.read_bytes()
    if zipped!=source_bytes:raise ValueError('main.tex changed during packaging')
    return {'passed':True,'output':str(out.relative_to(project)),'main':main,
            'main_sha256':digest(source_bytes),'source_tree_sha256':source_tree_digest(src),
            'files':len(files),'members':names}

def main_cli()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',type=Path,required=True)
    ap.add_argument('--source-dir',default='manuscript/latex')
    ap.add_argument('--main',default='main.tex')
    ap.add_argument('--output',default='manuscript/overleaf-project.zip')
    ap.add_argument('--report',default='team_control/overleaf-package.json')
    a=ap.parse_args()
    try:
        rep=build(a.project,a.source_dir,a.main,a.output);code=0
    except Exception as e:
        rep={'passed':False,'errors':[type(e).__name__+': '+str(e)]};code=3
    rp=inside(a.project.resolve(),a.report);rp.parent.mkdir(parents=True,exist_ok=True)
    rp.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(('PASS' if rep['passed'] else 'FAIL')+' overleaf package')
    return code

if __name__=='__main__':raise SystemExit(main_cli())
