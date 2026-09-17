"""Validate provenance; final compliance uses the identical shared validator."""
import argparse
from pathlib import Path
from audit_core import numeric_report, inside
from gate_output import emit

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--ledger',default='manuscript/numeric-provenance.json')
    p.add_argument('--output',default='team_control/numeric-provenance-report.json')
    a=p.parse_args();r=numeric_report(a.project,a.ledger)
    out=inside(a.project,a.output)
    emit(r,out,label='numeric provenance',failure_file=inside(a.project,a.ledger))
    return 0 if r['passed'] else 3
if __name__=='__main__':raise SystemExit(main())
