"""Bind reference/derivation inventory to the manuscript and source snapshots.

No online reliability oracle: reading and scientific source assessment remain required.
"""
import json,re
import argparse
from audit_core import inside,read,sha
from gate_output import emit
def report(project,paper,registry):
    errors=[]
    try:
        data=read(inside(project,registry))
        if data.get('paper_sha256')!=sha(inside(project,paper)) or data.get('paper')!=paper:errors.append('source registry stale or unbound')
        sources=data['sources'];claims=data['claims'];ids=[x['id'] for x in sources]
        if len(ids)!=len(set(ids)) or any(type(x)!=int or x<1 for x in ids):errors.append('source IDs must be unique positive integers')
        if not isinstance(claims,list):errors.append('claims must be a list')
        for source in sources:
            kind=source['kind']
            required=['author','title','manuscript_locations','source_location','reliability_reason','reliability_evidence']
            required+= {'book':['place','publisher','pages','year'],'journal':['journal','volume_issue','pages_or_article_id','year'],'web':['url','accessed'],'problem':['year']}.get(kind,[])
            if kind not in ('book','journal','web','problem'):errors.append('unsupported source kind')
            for key in required:
                if not isinstance(source.get(key),str) or not source[key].strip():errors.append(f'source {source["id"]}: missing {key}')
            if kind=='web':
                if not re.match(r'https?://[^/\s]+',source.get('url','')):errors.append('invalid source URL')
                from datetime import date
                date.fromisoformat(source.get('accessed',''))
            snapshot=inside(project,source['snapshot'])
            if sha(snapshot)!=source['snapshot_sha256']:errors.append('source snapshot changed')
            if not snapshot.read_bytes():errors.append(f'source {source["id"]}: empty source snapshot')
            if source.get('verification')!='read_and_checked':errors.append('source not read and checked')
        for claim in claims:
            if not claim.get('location') or not claim.get('statement'):errors.append('claim location/statement missing')
            cited=claim.get('source_ids',[])
            if not isinstance(cited,list) or any(x not in ids for x in cited):errors.append('claim uses unknown source')
            if claim.get('origin')=='borrowed' and not cited:errors.append('borrowed claim without citation')
            elif claim.get('origin') not in ('borrowed','derived'):errors.append('claim origin missing')
            if claim.get('origin')=='derived':
                proof=inside(project,claim['derivation_file'])
                if sha(proof)!=claim['derivation_sha256'] or not claim.get('derivation_location'):errors.append('derivation missing or stale')
    except Exception as e:errors.append(type(e).__name__+': '+str(e))
    return {'passed':not errors,'errors':errors,'limitations':'Checks inventory bindings, not scientific correctness, source reliability, or completeness of unnumbered claims.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--paper',required=True);p.add_argument('--registry',default='manuscript/source-registry.json');p.add_argument('--output',required=True);a=p.parse_args()
    r=report(a.project,a.paper,a.registry);emit(r,inside(a.project,a.output),label='sources',failure_file=inside(a.project,a.paper));raise SystemExit(0 if r['passed'] else 3)
