"""Lightweight current-edition official-format gate.

Only explicit mandatory requirements can fail delivery. Official recommendations
produce warnings. Unspecified/ambiguous items are intentionally absent.
"""
import argparse
from audit_core import inside, read, sha
from gate_output import emit


def report(project, paper, checklist):
    errors, warnings = [], []
    try:
        data = read(inside(project, checklist))
        status = data.get('verification_status') or ('verified' if data.get('official_sources') else 'unverifiable')
        if status not in ('verified', 'unverifiable'):
            errors.append('verification_status must be verified or unverifiable')

        if data.get('search_attempted') is not True:
            errors.append('current-edition official-format lookup was not attempted')

        # Paper binding is useful but deliberately lightweight: stale/missing hashes warn,
        # because a text edit does not necessarily invalidate a format check.
        if data.get('paper') and data.get('paper') != paper:
            warnings.append('checklist paper path differs from current paper; refresh format notes if layout changed')
        stored_hash = str(data.get('paper_sha256') or '').strip()
        if stored_hash:
            try:
                if stored_hash != sha(inside(project, paper)):
                    warnings.append('checklist paper hash is stale; refresh format notes if layout changed')
            except Exception:
                warnings.append('could not verify checklist paper hash')

        sources = data.get('official_sources')
        if not isinstance(sources, list):
            errors.append('official_sources must be a list')
            sources = []

        if status == 'verified':
            if data.get('extraction_reviewed') is not True:
                errors.append('verified official sources require extraction_reviewed=true')
            if not sources:
                errors.append('verified status requires at least one current-edition official source')
        else:
            if not str(data.get('search_note', '')).strip():
                errors.append('unverifiable status requires search_note describing what was checked')
            warnings.append('current-edition official format could not be fully verified; format remains pending user confirmation')

        for i, src in enumerate(sources, 1):
            if not isinstance(src, dict) or not str(src.get('source', '')).strip() or not str(src.get('locator', '')).strip():
                errors.append(f'official source {i}: source and locator required')
                continue
            # Local snapshots can be hash-bound. Web URLs may intentionally have no local hash.
            if src.get('sha256'):
                try:
                    sp = inside(project, src['source'])
                    if not sp.is_file() or sha(sp) != src['sha256']:
                        errors.append(f'official source {i}: stale or missing source file')
                except Exception:
                    errors.append(f'official source {i}: stale or missing source file')

        items = data.get('items')
        if not isinstance(items, list):
            errors.append('items must be a list')
            items = []
        if status == 'verified' and not items:
            if not (data.get('no_explicit_format_requirements') is True and str(data.get('no_requirement_note', '')).strip()):
                warnings.append('no format items recorded; if the reviewed official sources truly contain none, record no_explicit_format_requirements=true')

        ids = []
        for row in items:
            if not isinstance(row, dict):
                errors.append('checklist item must be an object')
                continue
            key = str(row.get('id', '')).strip()
            ids.append(key)
            if not key:
                errors.append('item id missing')
            rule = str(row.get('rule', '')).strip()
            locator = str(row.get('source_locator', '')).strip()
            note = str(row.get('note', '')).strip()
            if not rule:
                errors.append((key or '?') + ': rule missing')
            if not locator:
                errors.append((key or '?') + ': source_locator missing')
            if not note:
                errors.append((key or '?') + ': explanation missing')

            strength = row.get('strength', 'mandatory')
            item_status = row.get('status')
            if strength == 'mandatory':
                if item_status not in ('pass', 'not_applicable'):
                    errors.append((key or '?') + ': mandatory status must be pass or not_applicable')
            elif strength == 'advisory':
                if item_status not in ('pass', 'warn', 'not_applicable', 'pending'):
                    errors.append((key or '?') + ': advisory status must be pass|warn|pending|not_applicable')
                elif item_status in ('warn', 'pending'):
                    warnings.append((key or '?') + ': advisory official guidance not fully applied')
            else:
                errors.append((key or '?') + ': strength must be mandatory or advisory')

            # Evidence is optional to keep format QA light. If supplied, it must be real;
            # a machine FAIL cannot be overridden by a handwritten pass.
            evidence = row.get('evidence', [])
            if evidence is None:
                evidence = []
            if not isinstance(evidence, list):
                errors.append((key or '?') + ': evidence must be a list when present')
                continue
            for e in evidence:
                if not isinstance(e, dict) or not e.get('file'):
                    errors.append((key or '?') + ': malformed evidence entry')
                    continue
                ep = inside(project, e['file'])
                if not ep.is_file():
                    errors.append((key or '?') + ': evidence file missing')
                    continue
                if e.get('sha256') and sha(ep) != e.get('sha256'):
                    errors.append((key or '?') + ': stale evidence')
                    continue
                if ep.suffix.lower() == '.json':
                    payload = read(ep)
                    if isinstance(payload, dict) and payload.get('passed') is False:
                        errors.append((key or '?') + ': machine FAIL cannot be overridden by checklist status')

        if len(ids) != len(set(ids)):
            errors.append('duplicate checklist item id')
    except Exception as e:
        errors.append(type(e).__name__ + ': ' + str(e))

    return {
        'passed': not errors,
        'errors': errors,
        'warnings': warnings,
        'scope': 'current-edition explicit official format requirements only',
        'policy': 'mandatory blocks; advisory warns; unspecified/ambiguous ignored',
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--project', required=True)
    p.add_argument('--paper', required=True)
    p.add_argument('--checklist', default='manuscript/official-checklist.json')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    r = report(a.project, a.paper, a.checklist)
    out = inside(a.project, a.output)
    emit(r, out, label='official clauses', failure_file=inside(a.project, a.paper))
    raise SystemExit(0 if r['passed'] else 3)
