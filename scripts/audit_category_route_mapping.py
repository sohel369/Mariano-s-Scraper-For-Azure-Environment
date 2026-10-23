#!/usr/bin/env python3
"""Audit the parent/child route mapping in the supplied CSVs. This is not a live crawl test."""
import csv, json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
original=BASE/'data/input/Marianos_Category_URLs_Original_Brief.csv'
children=BASE/'data/input/Marianos_Category_URLs.csv'
with original.open(newline='',encoding='utf-8-sig') as f: parents=list(csv.DictReader(f))
with children.open(newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
parent_urls={r.get('URL','').strip() for r in parents if r.get('URL','').strip()}
child_parent_urls={r.get('parent_url','').strip() for r in rows if r.get('parent_url','').strip()}
missing_parent_mapping=sorted(parent_urls-child_parent_urls)
unknown_parent_mapping=sorted(child_parent_urls-parent_urls)
missing_child_fields=[i+2 for i,r in enumerate(rows) if not r.get('URL','').strip() or not r.get('sub_category','').strip()]
report={
 'audit_type':'CSV CONFIGURATION MAPPING ONLY',
 'original_parent_rows':len(parents),
 'unique_original_parent_urls':len(parent_urls),
 'child_route_rows':len(rows),
 'unique_child_urls':len({r.get('URL','').strip() for r in rows if r.get('URL','').strip()}),
 'parent_urls_without_child_mapping':missing_parent_mapping,
 'child_rows_with_unknown_parent_url':unknown_parent_mapping,
 'child_rows_missing_url_or_name':missing_child_fields,
 'mapping_structure_pass':bool(len(parents)==28 and len(parent_urls)==28 and len(rows)==28 and not missing_parent_mapping and not unknown_parent_mapping and not missing_child_fields),
 'does_not_prove_live_route_visits_or_pagination':True
}
out=BASE/'logs/category_route_mapping_structure_audit.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['mapping_structure_pass'] else 1)
