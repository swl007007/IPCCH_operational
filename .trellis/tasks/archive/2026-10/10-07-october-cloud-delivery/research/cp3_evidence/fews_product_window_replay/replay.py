"""Independent actual product-wrapper replay against frozen April accepted exports."""
import hashlib, json, resource, runpy, sys, time, traceback
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path('/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational')
OUT = Path('/tmp/oct-fews-product-window-evidence')
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO))
base = runpy.run_path(str(REPO / '.trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/fews_frozen_replay/replay.py'))
sha, numeric, exact = (base[k] for k in ('sha', 'numeric', 'exact'))
ROOT, SUITE, PANEL, PANEL_SHA = (base[k] for k in ('ROOT', 'SUITE', 'PANEL', 'PANEL_SHA'))
from cloud.orchestrator import delivery_scoring as ds
from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder, MaxPlusImputer
from sklearn.ensemble import RandomForestClassifier

def no_fit(*args, **kwargs):
    raise AssertionError('fit must not run')
for cls in (Stage3FeatureBuilder, MaxPlusImputer, RandomForestClassifier):
    cls.fit = no_fit

paths = [REPO / 'cloud/orchestrator/delivery_scoring.py', REPO / 'cloud/orchestrator/delivery_inputs.py']
for directory in ('core', 'local', 'assets', 'schemas'):
    paths += [p for p in (REPO / 'fewsnet_partitioned_rf_pipeline' / directory).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
paths += [p for p in (ROOT / 'model_artifacts' / SUITE).rglob('*') if p.is_file()]
start = time.monotonic()
report = {'status': 'incomplete', 'origin': '2026-04', 'scopes': {}, 'python': sys.executable,
          'identity_source': 'frozen normalized April panel (baseline replay only)',
          'source_before': {str(p.relative_to(REPO)): sha(p) for p in paths}}

def save(stage):
    report.update(stage=stage, elapsed_seconds=time.monotonic()-start,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(stage, round(report['elapsed_seconds'], 2), report['peak_rss_kib'], flush=True)

try:
    report['panel_sha256'] = sha(PANEL)
    assert report['panel_sha256'] == PANEL_SHA
    identity, window = ds.load_fewsnet_scoring_inputs(PANEL, '2026-04', identity_path=PANEL)
    report['identity_rows'], report['window_rows'] = len(identity), len(window)
    save('inputs_loaded')
    artifact_paths = {h: f'model_artifacts/{SUITE}/{h}m' for h in (0,6,12)}
    results = ds.score_fewsnet(window, {h: ROOT / artifact_paths[h] for h in (0,6,12)},
                              identity_panel=identity, origin='2026-04', source_input=str(PANEL),
                              artifact_paths=artifact_paths)
    saved_summary = json.loads((ROOT / 'predictions/202604/run_summary.json').read_text())
    for h, result in results.items():
        path = ROOT / f'predictions/202604/fewsnet_partitioned_rf_202604_scope_{h}m_predictions.csv'
        assert sha(path) == saved_summary['horizons'][f'{h}m']['prediction']['sha256']
        a = result['predictions'].set_index('admin_code').sort_index()
        b = base['_read_local_prediction_csv'](path).set_index('admin_code').sort_index()
        assert a.index.equals(b.index) and a.index.is_unique
        nums = {c: numeric(a[c], b[c]) for c in ('probability_crisis','threshold','population','lat','lon')}
        discrete = {c: exact(a[c], b[c]) for c in ('predicted_crisis','cluster_id','prediction_source',
                    'feature_month','target_month','horizon_months','population_reference_period','population_source',
                    'suite_version','model_artifact_path','ADMIN0','ADMIN1','ADMIN2','ADMIN3','ISO3')}
        matrix = result['inference_frame'][list(result['rules'])].apply(pd.to_numeric, errors='coerce')
        actual_missing = ~np.isfinite(matrix.to_numpy(dtype=float))
        missing_equal = np.array_equal(actual_missing, result['final_missing'].to_numpy())
        passed = all(v['mismatches']==0 for v in [*nums.values(),*discrete.values()]) and missing_equal
        report['scopes'][str(h)] = {'rows':len(a),'numeric':nums,'exact':discrete,'passed':passed,
                                  'missing_mask_equal':missing_equal,'missing_cells':int(actual_missing.sum()),
                                  'saved_prediction_sha256':sha(path),'package_id':result['package_id']}
    report['source_after'] = {str(p.relative_to(REPO)): sha(p) for p in paths}
    report['source_unchanged'] = report['source_before'] == report['source_after']
    report['status'] = 'passed' if report['source_unchanged'] and all(s['passed'] for s in report['scopes'].values()) else 'mismatch'
except BaseException as exc:
    report.update(status='error', error=repr(exc), traceback=traceback.format_exc())
    traceback.print_exc()
finally:
    save('complete')
raise SystemExit(0 if report['status']=='passed' else 1)
