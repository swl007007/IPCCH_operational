"""Supervisor experiment: 13-month Stage3 window with full-history output population."""
import gc, json, resource, runpy, sys, time, traceback
from pathlib import Path

import pandas as pd

REPO = Path('/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational')
sys.path.insert(0, str(REPO))
OUT = Path('/tmp/oct-fews-window-evidence')
OUT.mkdir(exist_ok=True)
base = runpy.run_path(str(REPO / '.trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/fews_frozen_replay/replay.py'))
sha, numeric, exact = (base[k] for k in ('sha', 'numeric', 'exact'))
ROOT, SUITE, PANEL, PANEL_SHA = (base[k] for k in ('ROOT', 'SUITE', 'PANEL', 'PANEL_SHA'))
from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
from fewsnet_partitioned_rf_pipeline.local.outputs import build_identity_population_frame, enrich_local_predictions, _RAW_REQUIRED_COLUMNS
from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder, MaxPlusImputer
from fewsnet_partitioned_rf_pipeline.core.horizons import select_latest_inference_frame
from sklearn.ensemble import RandomForestClassifier

def no_fit(*args, **kwargs):
    raise AssertionError('fit must never run')
MaxPlusImputer.fit = no_fit
RandomForestClassifier.fit = no_fit
Stage3FeatureBuilder.fit = no_fit
paths = ['fewsnet_partitioned_rf_pipeline/core/' + p + '.py' for p in ('preprocessing', 'horizons', 'inference')]
paths += ['fewsnet_partitioned_rf_pipeline/local/' + p + '.py' for p in ('outputs', 'package')]
start = time.monotonic()
report = {'status': 'incomplete', 'origin': '2026-04', 'calendar_window': ['2025-04', '2026-04'],
          'population_input': 'full normalized history with required identity/population columns',
          'source_sha256_before': {p: sha(REPO / p) for p in paths}, 'scopes': {}, 'python': sys.executable}

def save(stage):
    report.update(stage=stage, elapsed_seconds=time.monotonic()-start,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(stage, round(report['elapsed_seconds'], 2), report['peak_rss_kib'], flush=True)

try:
    report['input_sha256'] = sha(PANEL)
    assert report['input_sha256'] == PANEL_SHA
    full_identity_source = pd.read_csv(PANEL, usecols=list(_RAW_REQUIRED_COLUMNS), dtype={'FEWSNET_admin_code': 'string'})
    identity, population = build_identity_population_frame(full_identity_source, '2026-04')
    report['full_history_rows'] = len(full_identity_source)
    report['original_universe_rows'] = len(identity)
    del full_identity_source
    gc.collect()
    save('full_history_identity_complete')
    blocks = []
    for chunk in pd.read_csv(PANEL, chunksize=40000, dtype={'FEWSNET_admin_code': 'string'}, low_memory=False):
        month = chunk.date.astype(str).str[:7]
        blocks.append(chunk.loc[month.between('2025-04', '2026-04')].copy())
    window = pd.concat(blocks, ignore_index=True)
    del blocks, chunk
    gc.collect()
    report['window_rows'] = len(window)
    save('window_loaded')
    features = None
    saved_summary = json.loads((ROOT / 'predictions/202604/run_summary.json').read_text())
    for h in (0, 6, 12):
        loaded = load_local_model_package(ROOT / 'model_artifacts' / SUITE / f'{h}m')
        predictor = loaded.predictor
        if features is None:
            contract_columns = tuple(predictor.feature_contract.feature_columns)
            features = Stage3FeatureBuilder().transform(window, predictor.feature_contract)
            del window
        assert tuple(predictor.feature_contract.feature_columns) == contract_columns
        frame = select_latest_inference_frame(features, '2026-04', h)
        assert set(frame.admin_code) == set(identity.admin_code)
        predictions = enrich_local_predictions(predictor.predict_frame(frame), identity,
                       model_artifact_path=f'model_artifacts/{SUITE}/{h}m', source_input=str(PANEL))
        path = ROOT / f'predictions/202604/fewsnet_partitioned_rf_202604_scope_{h}m_predictions.csv'
        assert sha(path) == saved_summary['horizons'][f'{h}m']['prediction']['sha256']
        saved = base['_read_local_prediction_csv'](path)
        a, b = predictions.set_index('admin_code').sort_index(), saved.set_index('admin_code').sort_index()
        assert a.index.equals(b.index) and not a.index.duplicated().any()
        nums = {c: numeric(a[c], b[c]) for c in ('probability_crisis', 'threshold', 'population', 'lat', 'lon')}
        discrete = {c: exact(a[c], b[c]) for c in ('predicted_crisis', 'cluster_id', 'prediction_source',
              'feature_month', 'target_month', 'horizon_months', 'population_reference_period', 'population_source')}
        ok = all(v['mismatches'] == 0 for v in (*nums.values(), *discrete.values()))
        report['scopes'][str(h)] = {'rows': len(a), 'scores_and_population': nums, 'exact_fields': discrete,
                                   'passed': ok, 'threshold': float(predictor.threshold), 'model_checksums': loaded.checksums}
        del predictor, loaded, frame, predictions
        gc.collect()
        save(f'scope_{h}_complete')
    report['source_sha256_after'] = {p: sha(REPO / p) for p in paths}
    report['source_unchanged'] = report['source_sha256_before'] == report['source_sha256_after']
    report['status'] = 'passed' if report['source_unchanged'] and all(v['passed'] for v in report['scopes'].values()) else 'mismatch'
except BaseException as exc:
    report.update(status='error', error=repr(exc), traceback=traceback.format_exc())
    traceback.print_exc()
finally:
    save('complete')
raise SystemExit(0 if report['status'] == 'passed' else 1)
