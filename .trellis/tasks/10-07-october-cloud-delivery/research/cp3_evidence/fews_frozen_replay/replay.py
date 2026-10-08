"""Read-only frozen April FEWS replay; report only under this /tmp directory."""
from __future__ import annotations
import gc
import hashlib
import importlib.metadata as metadata
import json
import platform
import resource
import subprocess
import sys
import time
import traceback
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path('/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational')
OUT = Path(__file__).parent
sys.path.insert(0, str(REPO))
from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder, load_feature_contract
from fewsnet_partitioned_rf_pipeline.core.horizons import select_latest_inference_frame
from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
from fewsnet_partitioned_rf_pipeline.local.outputs import build_identity_population_frame, enrich_local_predictions, validate_local_prediction_frame, _read_local_prediction_csv

SUITE = 'local-202604-57cb3b981198-510375f58cd8'
ROOT = REPO / 'Outcome/fewsnet_partitioned_rf'
PANEL = ROOT / 'raw/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv'
PANEL_SHA = '510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d'
START = time.monotonic()
REPORT = {'status':'incomplete', 'scopes':{}, 'tolerance':{'rtol':0,'atol':1e-12}, 'byte_identical_required':False,
    'command': '/home/swl007007/.venvs/ipcch-h5-202609/bin/python -B ' + str(Path(__file__)),
    'environment':{'executable':sys.executable, 'python':platform.python_version(), 'libraries':{n:metadata.version(n) for n in ('numpy','pandas','scipy','scikit-learn','joblib','imbalanced-learn','xgboost','geopandas','pyarrow')}}}

def sha(path):
    d=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): d.update(b)
    return d.hexdigest()

def checkpoint(stage):
    REPORT['stage']=stage
    REPORT['elapsed_seconds']=round(time.monotonic()-START,3)
    REPORT['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (OUT/'report.json').write_text(json.dumps(REPORT,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'stage':stage,'elapsed_seconds':REPORT['elapsed_seconds'],'peak_rss_kib':REPORT['peak_rss_kib']}),flush=True)

def numeric(left,right):
    a=pd.to_numeric(left,errors='raise').to_numpy(dtype=float,na_value=np.nan)
    b=pd.to_numeric(right,errors='raise').to_numpy(dtype=float,na_value=np.nan)
    equal=np.isclose(a,b,rtol=0,atol=1e-12,equal_nan=True)
    delta=np.abs(a-b)
    finite=delta[np.isfinite(delta)]
    return {'mismatches':int((~equal).sum()),'max_abs_diff':float(finite.max()) if len(finite) else 0.0}

def exact(left,right):
    a=left.astype('string').fillna('<NULL>')
    b=right.astype('string').fillna('<NULL>')
    return {'mismatches':int(a.ne(b).sum())}

def main():
    assert numeric(pd.Series([1,np.nan]),pd.Series([1+5e-13,np.nan]))['mismatches']==0
    assert numeric(pd.Series([1]),pd.Series([1+5e-11]))['mismatches']==1
    assert exact(pd.Series(['01']),pd.Series(['1']))['mismatches']==1
    REPORT['comparison_selfcheck']='passed'
    REPORT['repository_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    paths=['fewsnet_partitioned_rf_pipeline/core/preprocessing.py','fewsnet_partitioned_rf_pipeline/core/horizons.py','fewsnet_partitioned_rf_pipeline/core/inference.py','fewsnet_partitioned_rf_pipeline/local/package.py','fewsnet_partitioned_rf_pipeline/local/outputs.py']
    REPORT['current_source_sha256']={p:sha(REPO/p) for p in paths}
    saved_summary=ROOT/'predictions/202604/run_summary.json'
    REPORT['saved_run_summary_sha256']=sha(saved_summary)
    summary=json.loads(saved_summary.read_text())
    checkpoint('hashing_frozen_panel')
    REPORT['source_input']={'path':str(PANEL),'sha256':sha(PANEL),'size_bytes':PANEL.stat().st_size}
    assert REPORT['source_input']['sha256']==PANEL_SHA, 'frozen panel SHA mismatch'
    checkpoint('reading_full_frozen_panel')
    contract=load_feature_contract(ROOT/'model_artifacts'/SUITE/'0m/feature_contract.json')
    panel=pd.read_csv(PANEL,dtype={'FEWSNET_admin_code':'string'},low_memory=False)
    REPORT['source_input']['rows']=len(panel)
    assert len(panel)==1120728
    checkpoint('building_identity_and_frozen_features')
    identity,pop_summary=build_identity_population_frame(panel,'2026-04')
    features=Stage3FeatureBuilder().transform(panel,contract)
    latest=select_latest_inference_frame(features,'2026-04',0)
    REPORT['full_feature_rows']=len(features)
    REPORT['latest_feature_rows']=len(latest)
    del panel,features
    gc.collect()
    checkpoint('full_panel_transformed')
    for h in (0,6,12):
        key=f'{h}m'
        package=ROOT/'model_artifacts'/SUITE/key
        checkpoint('loading_'+key)
        loaded=load_local_model_package(package,expected_suite_version=SUITE,expected_panel_sha256=PANEL_SHA)
        assert loaded.predictor.feature_contract==contract
        frame=latest.drop(columns=['target_month'])
        frame=select_latest_inference_frame(frame,'2026-04',h)
        formal=loaded.predictor.predict_frame(frame)
        replay=enrich_local_predictions(formal,identity,model_artifact_path=f'model_artifacts/{SUITE}/{key}',source_input=str(PANEL))
        target=str(pd.Period('2026-04',freq='M')+h)
        validation=validate_local_prediction_frame(replay,expected_admin_codes=latest['admin_code'].tolist(),feature_month='2026-04',target_month=target,horizon_months=h,suite_version=SUITE)
        saved_path=ROOT/'predictions/202604'/f'fewsnet_partitioned_rf_202604_scope_{key}_predictions.csv'
        saved=_read_local_prediction_csv(saved_path)
        saved_sha=sha(saved_path)
        assert saved_sha==summary['horizons'][key]['prediction']['sha256']
        keys=['admin_code','feature_month','target_month','horizon_months']
        keyed=lambda f:set(map(tuple,f[keys].astype(str).to_numpy()))
        scope={'rows':{'replay':len(replay),'saved':len(saved)},'native_keys':keys,
            'key_sets_equal':keyed(replay)==keyed(saved),'duplicate_keys':{'replay':int(replay.duplicated(keys).sum()),'saved':int(saved.duplicated(keys).sum())},
            'saved_prediction_sha256':saved_sha,'model_joblib_sha256':sha(package/'model.joblib'),
            'package_checksums':loaded.checksums,'source_git_commit':loaded.manifest['source_git_commit'],
            'threshold':float(loaded.predictor.threshold),'feature_count':len(contract.feature_columns),
            'validation':validation,'scores':{},'discrete_dates_horizons':{},'metadata':{}}
        assert set(replay.admin_code)==set(saved.admin_code)
        assert replay.admin_code.is_unique and saved.admin_code.is_unique
        a=replay.set_index('admin_code').sort_index()
        b=saved.set_index('admin_code').sort_index()
        for c in ('probability_crisis','threshold'): scope['scores'][c]=numeric(a[c],b[c])
        for c in ('predicted_crisis','cluster_id','prediction_source','feature_month','target_month','horizon_months'):
            scope['discrete_dates_horizons'][c]=exact(a[c],b[c])
        for c in ('lat','lon','population'): scope['metadata'][c]=numeric(a[c],b[c])
        for c in ('ADMIN0','ADMIN1','ADMIN2','ADMIN3','ISO3','population_reference_period','population_source','suite_version','model_artifact_path','source_input'):
            scope['metadata'][c]=exact(a[c],b[c])
            if scope['metadata'][c]['mismatches']:
                mismatch=a[c].astype('string').fillna('<NULL>').ne(b[c].astype('string').fillna('<NULL>'))
                scope['metadata'][c]['examples']=[{'admin_code':str(i),'replay':str(a.loc[i,c]),'saved':str(b.loc[i,c])} for i in a.index[mismatch][:3]]
        scope['score_and_key_parity']=scope['key_sets_equal'] and not any(scope['duplicate_keys'].values()) and all(v['mismatches']==0 for group in ('scores','discrete_dates_horizons') for v in scope[group].values())
        REPORT['scopes'][key]=scope
        del loaded,formal,replay,saved,a,b,frame
        gc.collect()
        checkpoint('completed_'+key)
    REPORT['status']='passed' if all(x['score_and_key_parity'] for x in REPORT['scopes'].values()) else 'mismatch'
    REPORT['exit_status']=0 if REPORT['status']=='passed' else 1
    checkpoint('complete')
    return REPORT['exit_status']

if __name__=='__main__':
    try: code=main()
    except BaseException as exc:
        REPORT['status']='error'
        REPORT['error']=repr(exc)
        REPORT['traceback']=traceback.format_exc()
        REPORT['exit_status']=2
        checkpoint('exception')
        traceback.print_exc()
        code=2
    raise SystemExit(code)
