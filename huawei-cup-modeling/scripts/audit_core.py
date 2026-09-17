"""Shared fail-closed evidence validation; self-reported flags are not evidence."""
from pathlib import Path
import hashlib,json,math,re,os,shutil,subprocess,tempfile
VISUAL=('typography_and_hierarchy','math_and_cjk_glyphs','tables_figures_captions','layout_and_readability','evidence_labels_and_references')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _pdftoppm():
    configured=os.environ.get('HUAWEI_POPPLER_BIN')
    candidates=[]
    if configured:candidates.append(Path(configured)/('pdftoppm.exe' if os.name=='nt' else 'pdftoppm'))
    found=shutil.which('pdftoppm')
    if found:candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():return str(candidate)
    return None
def inside(root,value):
    root=Path(root).resolve(); p=(root/str(value)).resolve()
    if not p.is_relative_to(root): raise ValueError('evidence path escapes project')
    return p
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def validation_evidence_sha(project,rel):
    """A validation carrier must exist; an explicit machine FAIL is not evidence of success."""
    p=inside(project,rel)
    if not p.is_file() or not p.read_bytes().strip():raise ValueError('validation evidence missing or empty: '+str(rel))
    if p.suffix.lower()=='.json':
        payload=read(p)
        if isinstance(payload,dict) and 'passed' in payload and payload['passed'] is not True:
            raise ValueError('validation evidence contains a machine FAIL or non-boolean verdict: '+str(rel))
    return sha(p)
def resolve(root,expr):
    if not isinstance(expr,str): raise ValueError('field must be a string')
    m=re.fullmatch(r'(max|min)\((.+)\)',expr)
    if m:
        v=resolve(root,m[2])
        if not isinstance(v,list) or not v: raise ValueError('aggregate needs nonempty list')
        return (max if m[1]=='max' else min)(v)
    if not re.fullmatch(r'[A-Za-z_]\w*(?:(?:\.[A-Za-z_]\w*)|(?:\[(?:\d+|\*|\d*:\d*)\]))*',expr): raise ValueError('unsupported field')
    def visit(obj,parts):
        if not parts:return obj
        k,*tail=parts
        if isinstance(obj,dict):return visit(obj[k],tail)
        if isinstance(obj,list):
            if k=='*':return [visit(x,tail) for x in obj]
            if ':' in k:
                a,b=k.split(':');return [visit(x,tail) for x in obj[slice(int(a) if a else None,int(b) if b else None)]]
            return visit(obj[int(k)],tail)
        raise ValueError('field cannot resolve')
    return visit(root,[p for p in re.split(r'\.|\[|\]',expr) if p])
def same(a,b):
    if isinstance(a,bool) or isinstance(b,bool):return type(a)==type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        if not math.isfinite(a) or not math.isfinite(b):return False
        if isinstance(a,int) and isinstance(b,int):return a==b
        return math.isclose(a,b,rel_tol=1e-12,abs_tol=0.0)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,dict) and isinstance(b,dict):return bool(a) and set(a)==set(b) and all(same(v,b[k]) for k,v in a.items())
    return type(a)==type(b) and a==b
def has_number(value):
    if isinstance(value,bool):return False
    if isinstance(value,(int,float)):return math.isfinite(value)
    if isinstance(value,dict):return any(has_number(v) for v in value.values())
    if isinstance(value,list):return any(has_number(v) for v in value)
    return False
def apply_rounding(raw,rule):
    """Compute the manuscript display value from a raw run value under a rounding rule."""
    rule=(rule or 'asis').strip()
    if rule in ('asis','','raw'):return float(raw)
    m=re.fullmatch(r'round\((\d+)\)',rule)
    if m:return round(float(raw),int(m[1]))
    if rule=='int':return float(round(float(raw)))
    m=re.fullmatch(r'percent\((\d+)\)',rule)
    if m:return round(float(raw)*100,int(m[1]))
    m=re.fullmatch(r'(floor|ceil)\((\d+)\)',rule)
    if m:
        n=int(m[2]);f=math.floor if m[1]=='floor' else math.ceil
        return f(float(raw)*(10**n))/(10**n)
    raise ValueError('unsupported rounding_rule: '+rule)
def display_consistent(item,raw):
    """Check display_value == round(raw, rounding_rule) within tolerance. True when no display declared."""
    if 'display_value' not in item:return True,''
    if raw is None:return False,'display_value declared without a raw run value'
    if isinstance(raw,bool) or isinstance(item['display_value'],bool):return False,'raw/display values must not be boolean'
    try:expected=apply_rounding(raw,item.get('rounding_rule','asis'))
    except (ValueError,TypeError,OverflowError) as e:return False,str(e)
    try:dv=float(item['display_value'])
    except (TypeError,ValueError,OverflowError):return False,'display_value is not numeric'
    if not math.isfinite(expected) or not math.isfinite(dv):return False,'raw/display values must be finite'
    tol=item.get('tolerance')
    if tol is not None:
        if isinstance(tol,bool):return False,'tolerance must not be boolean'
        try:tol=float(tol)
        except (TypeError,ValueError,OverflowError):return False,'tolerance is not numeric'
        if not math.isfinite(tol) or tol<0:return False,'tolerance must be finite and nonnegative'
        ok=abs(expected-dv)<=tol
    else:ok=math.isclose(expected,dv,rel_tol=1e-9,abs_tol=0.0)
    return ok,('' if ok else f"display {item['display_value']} != round(raw,{item.get('rounding_rule','asis')})={expected}")
def _check_independent(project,item,problems,min_checks):
    checks=item.get('independent_checks',[])
    if not isinstance(checks,list):problems.append('independent_checks must be a list');return
    if len(checks)<min_checks:problems.append(f'tier requires at least {min_checks} independent check(s)')
    seen=set();check_files=set()
    for c in checks:
        try:
            cp=inside(project,c['file'])
            if sha(cp)!=c['sha256']:problems.append('check hash changed')
            if resolve(read(cp),c['field']) is not True:problems.append('check did not pass')
            seen.add((str(cp),c['field']));check_files.add(str(cp))
        except (KeyError,TypeError,IndexError,ValueError,OSError) as e:problems.append(str(e))
    if min_checks>=2:
        if len(seen)<2:problems.append('duplicate checks')
        if len(check_files)<2:problems.append('independent checks must use different files')
def numeric_report(project,ledger):
    """Validate numeric provenance, not scientific sufficiency.

    Schema 3 binds displayed numbers to real runs. Tier A/B require manuscript/display
    binding; Tier C only requires the run binding. Optional independent_checks are
    validated when present, while scientific validation strength is enforced once in
    run-state rather than duplicated here.
    """
    errors=[];rows=[]
    try:
        data=read(inside(project,ledger))
        schema=data.get('schema_version')
        if schema != 3:raise ValueError('ledger schema_version must be 3; regenerate bindings from current runs')
        records=data.get('results')
        if not isinstance(records,list) or not records:raise ValueError('empty results')
        for item in records:
            result={'artifact':item.get('artifact')};problems=[]
            try:
                if not isinstance(item.get('artifact'),str) or not item['artifact'].strip():problems.append('artifact label required')
                p=inside(project,item['run_file'])
                if sha(p)!=item['run_sha256']:problems.append('run hash changed')
                actual=resolve(read(p),item['field'])
                if not has_number(actual):problems.append('result contains no finite numeric value')
                raw=item['raw_value'] if 'raw_value' in item else item.get('value')
                if 'value' in item and not same(item['value'],actual):problems.append('value mismatch')
                if 'raw_value' in item and not same(item['raw_value'],actual):problems.append('raw_value mismatch')
                if 'value' not in item and 'raw_value' not in item:problems.append('value or raw_value required')
                tier=str(item.get('tier','A')).upper();result['tier']=tier
                if tier not in ('A','B','C'):problems.append('tier must be A, B or C')
                if tier in ('A','B'):
                    if not isinstance(item.get('manuscript_location'),str) or not item['manuscript_location'].strip():problems.append('manuscript_location required for tier '+tier)
                    if 'display_value' not in item:problems.append('display_value required for tier '+tier)
                    if not isinstance(item.get('rounding_rule'),str) or not item['rounding_rule'].strip():problems.append('rounding_rule required for tier '+tier)
                    ok,err=display_consistent(item,raw if raw is not None else actual)
                    if not ok:problems.append(err or 'display binding failed')
                _check_independent(project,item,problems,0)
                result['actual']=actual
            except (KeyError,TypeError,IndexError,ValueError,OSError) as e:problems.append(str(e))
            result.update(passed=not problems,errors=problems);rows.append(result)
    except (ValueError,OSError,TypeError,AttributeError) as e:errors.append(str(e))
    return {'passed':not errors and bool(rows) and all(r['passed'] for r in rows),'errors':errors,'results':rows,'independence_note':'Distinct check evidence validated; scientific independence needs human/model review.'}
def theoretical_report(project,manifest='manuscript/theoretical-evidence.json'):
    """Evidence carrier for non-computational (theory/proof/construction) questions.

    This is NOT a bypass: it swaps run-bound numeric evidence for hash-bound proof
    evidence. Fail-closed on an empty or unbound manifest; proof CORRECTNESS still
    requires human/model review (mirrors the numeric independence_note)."""
    errors=[];rows=[]
    try:
        data=read(inside(project,manifest))
        claims=data.get('claims')
        if not isinstance(claims,list) or not claims:raise ValueError('theoretical-evidence claims empty; a theoretical submission still needs bound proof artifacts')
        kinds={'theorem','lemma','proposition','construction','counterexample','symbolic','derivation','proof'}
        for item in claims:
            row={'statement':item.get('statement')};problems=[]
            try:
                if not isinstance(item.get('statement'),str) or not item['statement'].strip():problems.append('statement required')
                if not isinstance(item.get('question'),str) or not re.fullmatch(r'Q[1-9][0-9]*',item['question']):problems.append('question id required (e.g. Q1)')
                if str(item.get('kind','')).lower() not in kinds:problems.append('kind must be one of '+ '/'.join(sorted(kinds)))
                if not isinstance(item.get('location'),str) or not item['location'].strip():problems.append('manuscript location required')
                pf=inside(project,item['proof_file'])
                if not pf.is_file() or not pf.read_bytes():problems.append('proof_file missing or empty')
                elif sha(pf)!=item.get('proof_sha256'):problems.append('proof hash changed')
                for c in item.get('independent_checks',[]) or []:
                    cp=inside(project,c['file'])
                    if sha(cp)!=c['sha256']:problems.append('check hash changed')
                    if resolve(read(cp),c['field']) is not True:problems.append('check did not pass')
            except (KeyError,TypeError,IndexError,ValueError,OSError) as e:problems.append(str(e))
            row.update(passed=not problems,errors=problems);rows.append(row)
    except (ValueError,OSError,TypeError,AttributeError) as e:errors.append(str(e))
    return {'passed':not errors and bool(rows) and all(r['passed'] for r in rows),'errors':errors,'results':rows,'independence_note':'Bound proof artifacts validated; mathematical correctness needs human/model review.'}

def route_report(project,path,expected_question=None):
    """Validate three distinct falsification lenses without forcing fake extra files."""
    errors=[]
    try:
        rows=read(inside(project,path))['iterations']
        if not isinstance(rows,list) or len(rows)<3:raise ValueError('ARCHITECT/SKEPTIC/REVIEWER iterations required')
        lenses=[];changes=set()
        allowed={'architect','skeptic','reviewer'}
        for row in rows:
            if expected_question and row.get('question')!=expected_question:raise ValueError('route evidence belongs to a different question')
            for key in ('question','lens','evidence','finding','change','risk'):
                if not isinstance(row.get(key),str) or not row[key].strip():raise ValueError('missing iteration '+key)
            lens=row['lens'].strip().lower()
            if lens not in allowed:raise ValueError('lens must be architect|skeptic|reviewer')
            lenses.append(lens)
            evidence=inside(project,row['evidence'])
            if not evidence.is_file() or not evidence.read_bytes():raise ValueError('missing or empty route evidence')
            changes.add((row['finding'],row['change']))
        if set(lenses)!=allowed:raise ValueError('route review must contain ARCHITECT, SKEPTIC and REVIEWER lenses')
        if len(changes)<3:raise ValueError('three lenses must record distinct findings/changes')
    except (KeyError,TypeError,ValueError,OSError) as e:errors.append(str(e))
    return {'passed':not errors,'errors':errors}

def proof_report(project,paper,proof_file,final=False):
    errors=[]
    try:
        p=read(inside(project,proof_file));n=p.get('page_count')
        if type(n)!=int or n<=0:raise ValueError('page_count must be positive integer')
        if inside(project,p.get('rendered_path',''))!=inside(project,paper):errors.append('rendered path mismatch')
        for k,h in [('rendered_path','rendered_sha256'),('source_path','source_sha256')]:
            if sha(inside(project,p[k]))!=p[h]:errors.append(k+' changed')
        try:
            from package_overleaf import source_tree_digest
            source=inside(project,p['source_path'])
            if p.get('source_tree_sha256')!=source_tree_digest(source.parent):errors.append('LaTeX source tree changed after render')
        except Exception as e:
            errors.append('cannot verify LaTeX source tree: '+str(e))
        if any(p.get('visual_inspection',{}).get(k)!='pass' for k in VISUAL):errors.append('incomplete visual inspection')
        if p.get('visual_inspection',{}).get('defects')!=[]:errors.append('unresolved visual defects')
        images=p.get('page_images',[])
        if len(images)!=n or len(set(images))!=n:errors.append('exact page image count required')
        for im in images:
            if sha(inside(project,im))!=p.get('page_sha256',{}).get(im):errors.append('page image changed')
            from PIL import Image
            with Image.open(inside(project,im)) as page_image:
                if min(page_image.size)<100:errors.append('page image resolution implausible')
                page_image.verify()
        pdf=inside(project,p.get('rendered_pdf',paper))
        if Path(paper).suffix.lower()=='.pdf' and pdf!=inside(project,paper):errors.append('proof PDF is not the delivered PDF')
        from pypdf import PdfReader
        if len(PdfReader(pdf).pages)!=n:errors.append('actual PDF page count differs')
        binding=p.get('render_binding')
        if not isinstance(binding,dict) or binding.get('engine')!='pdftoppm' or type(binding.get('dpi')) is not int or binding['dpi']<=0 or binding.get('pdf_sha256')!=sha(pdf):
            errors.append('render binding missing or stale')
        else:
            renderer=_pdftoppm()
            if not renderer:errors.append('pdftoppm unavailable; cannot verify page images')
            else:
                try:
                    with tempfile.TemporaryDirectory() as td:
                        prefix=Path(td)/'page'
                        subprocess.run([renderer,'-png','-r',str(binding['dpi']),str(pdf),str(prefix)],check=True,capture_output=True,text=True)
                        generated=sorted(Path(td).glob('page-*.png'),key=lambda x:int(re.search(r'-(\d+)\.png$',x.name).group(1)))
                        if len(generated)!=n:errors.append('rendered page count differs from proof')
                        else:
                            for generated_path,declared in zip(generated,images):
                                if sha(generated_path)!=sha(inside(project,declared)):
                                    errors.append('page image does not match rendered PDF');break
                except (OSError,subprocess.CalledProcessError,ValueError) as e:errors.append('page render verification failed: '+str(e))
    except Exception as e:errors.append(type(e).__name__+': '+str(e))
    return {'passed':not errors,'errors':errors}
