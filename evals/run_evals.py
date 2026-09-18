"""Evaluate generated outputs against annotated source facts, separately from confidence."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.models.schema import ExtractedPolicy
from app.validation.engine import _iter_fields, _normalize_ws, evidence_quote_in_pages
from app.config import Settings
from app.ingestion.pdf import parse_pdf, sha256_file


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--outputs',type=Path,default=ROOT/'outputs/sample')
    parser.add_argument('--sources',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'evals/last_report.json')
    args=parser.parse_args()
    golden=json.loads((ROOT/'evals/golden.json').read_text())
    policies={}
    for file in sorted(args.outputs.glob('*.json')):
        p=ExtractedPolicy.model_validate_json(file.read_text())
        policies.setdefault(p.document.content_hash,p)
    report={'scope':golden['scope'],'unique_documents':len(policies),'checks_passed':0,'checks_total':0,'evidence_claims':0,'unsupported_claims':0,'source_evidence_checked':bool(args.sources),'failures':[],'per_document':[]}
    for case in golden['cases']:
        p=policies.get(case['sha256'])
        if p is None:
            report['failures'].append({'source':case['source_file'],'error':'missing output'})
            continue
        data=p.model_dump()
        passed=0
        for check in case['checks']:
            field=data
            for part in check['path'].split('.'):field=field[part]
            if check['property']=='contains':
                actual=json.dumps([field['value'],field['conditions'],field['raw_text']],ensure_ascii=False)
                ok=_normalize_ws(str(check['expected'])) in _normalize_ws(actual)
            else:
                actual=field[check['property']]
                ok=actual==check['expected']
            report['checks_total']+=1
            if ok:passed+=1;report['checks_passed']+=1
            else:report['failures'].append({'source':case['source_file'],**check,'actual':actual})
        if args.sources:
            source=args.sources/case['source_file']
            if sha256_file(source)!=case['sha256']:raise ValueError('Source content changed')
            pages={p.page_number:p.page_text for p in parse_pdf(source,Settings(ocr_enabled=False))}
            for path,field in _iter_fields(p):
                if field.value is None and field.status=='unknown':continue
                report['evidence_claims']+=1
                valid=bool(field.evidence) and all(e.source_file==p.document.filename and e.page_number in pages and evidence_quote_in_pages(e.quote,{e.page_number:pages[e.page_number]}) for e in field.evidence)
                if not valid:report['unsupported_claims']+=1;report['failures'].append({'source':case['source_file'],'path':path,'error':'unsupported citation'})
        report['per_document'].append({'source':case['source_file'],'checks_passed':passed,'checks_total':len(case['checks']),'completion':p.extraction_metadata.completion_status,'fields_found':p.validation.fields_found,'review_flags':p.validation.fields_requiring_review,'conflicts':p.validation.conflict_count})
    args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if report['failures'] or report['checks_total']==0:raise SystemExit(1)
if __name__=='__main__':main()
