from __future__ import annotations
import gc, json, resource, runpy, sys, time, traceback
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path('/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational')
OUT = Path(__file__).parent
BASELINE = REPO / '.trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/fews_frozen_replay/replay.py'
base = runpy.run_path(str(BASELINE))
sha, numeric, exact = base['sha'], base['numeric'], base['exact']
ROOT, SUITE, PANEL, PANEL_SHA = (base[k] for k in ('ROOT', 'SUITE', 'PANEL', 'PANEL_SHA'))
from cloud.orchestrator import delivery_scoring as wrapper
from fewsnet_partitioned_rf_pipeline.core.preprocessing import MaxPlusImputer
from sklearn.ensemble import RandomForestClassifier

SOURCE = REPO / 'cloud/orchestrator/delivery_scoring.py'
START = time.monotonic()
REPORT = {'status': 'incomplete', 'scopes': {}, 'command': '/usr/bin/time -v -o ' + str(OUT / 'time.txt') + ' timeout 180s /home/swl007007/.venvs/ipcch-h5-202609/bin/python -B ' + str(Path(__file__)), 'tolerance': {'rtol': 0, 'atol': 1e-12}, 'source_sha256_before': sha(SOURCE), 'python_executable': sys.executable}
assert REPORT['source_sha256_before'] == 'd403942d3eec094125b23c98e89beb037e785d222e7daa280bfa7650447b2663'
captured = {}

def checkpoint(stage):
    REPORT.update(stage=stage, elapsed_seconds=round(time.monotonic()-START,3), peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    (OUT / 'report.json').write_text(json.dumps(REPORT,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k: REPORT[k] for k in ('stage', 'elapsed_seconds', 'peak_rss_kib')}),flush=True)

def prohibit_fit(*args, **kwargs):
    raise AssertionError('fit called during frozen inference')

MaxPlusImputer.fit = prohibit_fit
RandomForestClassifier.fit = prohibit_fit
original_load = wrapper.load_local_model_package
def capture_load(path):
    loaded = original_load(path)
    predictor = loaded.predictor
    h = predictor.horizon_months
    captured[h] = {'feature_columns': tuple(predictor.feature_contract.feature_columns), 'imputer_values': np.asarray(predictor.imputer.impute_values_).copy(), 'n_features_in': int(predictor.imputer.n_features_in_), 'imputer_class': type(predictor.imputer).__name__, 'checksums': loaded.checksums}
    return loaded
wrapper.load_local_model_package = capture_load

original_select = wrapper.select_latest_inference_frame
def capture_select(features, origin, h):
    frame = original_select(features, origin, h)
    c = captured[h]
    raw_matrix = frame.loc[:, list(c['feature_columns'])].to_numpy(dtype=np.float64)
    c['expected_missing'] = pd.DataFrame(~np.isfinite(raw_matrix), columns=c['feature_columns'], index=frame['admin_code'].astype(str).to_numpy())
    c['raw_missing_cells'] = int((~np.isfinite(raw_matrix)).sum())
    return frame
wrapper.select_latest_inference_frame = capture_select

original_transform = wrapper.Stage3FeatureBuilder.transform
REPORT['transform_calls'] = 0
def capture_transform(self, panel, contract):
    REPORT['transform_calls'] += 1
    transformed = original_transform(self, panel, contract)
    REPORT['full_feature_rows'] = len(transformed)
    checkpoint('transformed_full_panel')
    return transformed
wrapper.Stage3FeatureBuilder.transform = capture_transform

def main():
    assert numeric(pd.Series([1,np.nan]),pd.Series([1+5e-13,np.nan]))['mismatches']==0
    assert numeric(pd.Series([1]),pd.Series([1+5e-11]))['mismatches']==1
    assert exact(pd.Series(['01']),pd.Series(['1']))['mismatches']==1
    REPORT['comparison_selfcheck']='passed'
    checkpoint('hashing_frozen_panel')
    REPORT['panel_sha256'] = sha(PANEL)
    assert REPORT['panel_sha256'] == PANEL_SHA
    panel = pd.read_csv(PANEL,dtype={'FEWSNET_admin_code':'string'},low_memory=False)
    REPORT['panel_rows']=len(panel)
    assert len(panel)==1120728
    checkpoint('calling_new_wrapper')
    results=wrapper.score_fewsnet(panel, {h: ROOT/'model_artifacts'/SUITE/f'{h}m' for h in (0,6,12)},origin='2026-04',source_input=str(PANEL),artifact_paths={h:f'model_artifacts/{SUITE}/{h}m' for h in (0,6,12)})
    del panel
    gc.collect()
    checkpoint('wrapper_returned')
    summary=json.loads((ROOT/'predictions/202604/run_summary.json').read_text())
    for h in (0,6,12):
        key=f'{h}m'
        result=results[h]
        replay=result['predictions']
        saved_path=ROOT/'predictions/202604'/f'fewsnet_partitioned_rf_202604_scope_{key}_predictions.csv'
        saved=base['_read_local_prediction_csv'](saved_path)
        saved_sha=sha(saved_path)
        assert saved_sha==summary['horizons'][key]['prediction']['sha256']
        keys=['admin_code','feature_month','target_month','horizon_months']
        keyed=lambda f:set(map(tuple,f[keys].astype(str).to_numpy()))
        a=replay.set_index('admin_code').sort_index()
        b=saved.set_index('admin_code').sort_index()
        scope={'rows':{'wrapper':len(replay),'saved':len(saved)},'key_sets_equal':keyed(replay)==keyed(saved),'duplicate_keys':{'wrapper':int(replay.duplicated(keys).sum()),'saved':int(saved.duplicated(keys).sum())},'scores':{c:numeric(a[c],b[c]) for c in ('probability_crisis','threshold')},'exact':{c:exact(a[c],b[c]) for c in ('predicted_crisis','cluster_id','prediction_source','feature_month','target_month','horizon_months')},'threshold':result['threshold'],'saved_sha256':saved_sha}
        c=captured[h]
        missing=result['final_missing']
        expected=c['expected_missing']
        expected_rules={feature:f'MaxPlusImputer[{feature}]={value!r}' for feature,value in zip(c['feature_columns'],c['imputer_values'])}
        scope['missingness_and_rules']={'feature_count':len(c['feature_columns']),'saved_imputer_class':c['imputer_class'],'saved_imputer_feature_count':c['n_features_in'],'saved_imputer_stat_count':len(c['imputer_values']),'columns_equal_actual_feature_columns':tuple(missing.columns)==c['feature_columns'],'index_equal_actual_scoring_frame':missing.index.equals(expected.index),'mask_equal_preimputation_nonfinite':missing.equals(expected),'missing_cells':c['raw_missing_cells'],'rules_equal_saved_imputer_values':result['rules']==expected_rules,'rule_count':len(result['rules']),'rule_examples':dict(list(result['rules'].items())[:3])}
        scope['parity_pass']=scope['key_sets_equal'] and not any(scope['duplicate_keys'].values()) and all(v['mismatches']==0 for group in ('scores','exact') for v in scope[group].values())
        m=scope['missingness_and_rules']
        scope['audit_fields_pass']=all(m[k] for k in ('columns_equal_actual_feature_columns','index_equal_actual_scoring_frame','mask_equal_preimputation_nonfinite','rules_equal_saved_imputer_values')) and m['feature_count']==m['saved_imputer_feature_count']==m['saved_imputer_stat_count']==m['rule_count']
        REPORT['scopes'][key]=scope
    REPORT['status']='passed' if all(s['parity_pass'] and s['audit_fields_pass'] for s in REPORT['scopes'].values()) else 'mismatch'
    REPORT['exit_status']=0 if REPORT['status']=='passed' else 1
    return REPORT['exit_status']

try:
    code=main()
except BaseException as exc:
    REPORT.update(status='error',error=repr(exc),traceback=traceback.format_exc(),exit_status=2)
    traceback.print_exc()
    code=2
finally:
    REPORT['source_sha256_after']=sha(SOURCE)
    REPORT['source_unchanged']=REPORT['source_sha256_before']==REPORT['source_sha256_after']
    checkpoint('complete')
raise SystemExit(code)
