"""Stream comparison of unchunked d and bounded-memory i, allowing only relocated audit source URI."""
import csv, hashlib, itertools, json
from pathlib import Path

left, right = Path('/tmp/oct-delivery-local-d'), Path('/tmp/oct-delivery-local-i')
def sha(p):
    digest = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()

paths = [f'inputs/{name}.csv' for name in ('ipcch_base_series','ipcch_origin_rows')]
paths += [str(p.relative_to(right)) for p in sorted(right.glob('scopes/*/ipcch/*.csv'))]
assert len(paths) == 17
report = {'files':{}, 'audit':{}}
for path in paths:
    a,b = sha(left/path),sha(right/path)
    report['files'][path] = {'left_sha256':a, 'right_sha256':b, 'byte_identical':a==b}
oldref = 'file:///tmp/oct-delivery-local-d/inputs/ipcch_base_series.csv#1'
newref = 'file:///tmp/oct-delivery-local-i/inputs/ipcch_base_series.csv#1'
count, bad, example = 0,0,None
with (left/'reports/ipcch_feature_fill_audit.csv').open(newline='') as a, (right/'reports/ipcch_feature_fill_audit.csv').open(newline='') as b:
    ra,rb=csv.DictReader(a),csv.DictReader(b)
    assert ra.fieldnames==rb.fieldnames
    for count,(x,y) in enumerate(itertools.zip_longest(ra,rb),1):
        assert x is not None and y is not None, 'audit row counts differ'
        assert x['source_ref']==oldref and y['source_ref']==newref
        x['source_ref']=newref
        if x!=y:
            bad+=1
            if example is None:
                example={'row':count,'fields':{k:[x[k],y[k]] for k in x if x[k]!=y[k]}}
report['audit']={'rows':count,'mismatches_after_exact_source_uri_relocation':bad,'first_mismatch':example}
report['status']='passed' if all(v['byte_identical'] for v in report['files'].values()) and bad==0 else 'mismatch'
Path('/tmp/oct-i-differential-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'audit':report['audit'],'nonidentical':[k for k,v in report['files'].items() if not v['byte_identical']]}))
raise SystemExit(0 if report['status']=='passed' else 1)
