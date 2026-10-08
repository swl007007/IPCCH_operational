import importlib.util, json, hashlib, sys, time, traceback
from pathlib import Path
import numpy as np
import pandas as pd
REPO=Path.cwd(); sys.path.insert(0,str(REPO))
TASK=REPO/'.trellis/tasks/10-07-october-cloud-delivery'
spec=importlib.util.spec_from_file_location('cp0', TASK/'research/cp0_replay_candidates.py')
cp0=importlib.util.module_from_spec(spec); spec.loader.exec_module(cp0)
source_paths=[REPO/'cloud/orchestrator/delivery_scoring.py', REPO/'model_pipeline/run_operational_launch_inference.py', REPO/'model_pipeline/ipcch_launch_runtime/model_package.py', REPO/'model_pipeline/ipcch_launch_runtime/adapters.py', REPO/'model_pipeline/ipcch_launch_runtime/feature_contract.py', REPO/'model_pipeline/ipcch_launch_runtime/inference.py']
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
report={'source_sha256_before':{str(p.relative_to(REPO)):sha(p) for p in source_paths},'started_epoch':time.time(),'scopes':{},'errors':[]}
try:
 from cloud.orchestrator.delivery_scoring import score_ipcch
 from model_pipeline import run_operational_launch_inference as launch
 from model_pipeline.ipcch_launch_runtime import adapters,model_package,feature_contract
 prior=json.loads((TASK/'research/cp0_evidence/cp0_replay_report.json').read_text())
 report['environment']=cp0.environment()
 report['input_sha256']=sha(REPO/cp0.IPCCH_INPUT)
 assert report['input_sha256']==cp0.IPCCH_INPUT_SHA256
 raw=launch._read_monthly_csv(REPO/cp0.IPCCH_INPUT)
 monthly,_=adapters.validate_monthly_input(raw,cp0.FEATURE_MONTH)
 print('START wrapper all 0/6/12; rows='+str(len(raw)),flush=True)
 scored=score_ipcch(raw,cp0.IPCCH_PACKAGE,origin=cp0.FEATURE_MONTH,source_input=cp0.IPCCH_INPUT)
 assert tuple(scored)==cp0.HORIZONS
 report['total_clipping']={str(p):0 for p in (2,3,4,5)}
 for scope in cp0.HORIZONS:
  result=scored[scope]; replay=result['predictions'].reset_index(drop=True)
  saved_path=cp0.IPCCH_SAVED/f'ipcch_launch_202604_scope_{scope}m_predictions.csv'
  saved=pd.read_csv(saved_path,dtype={'area_id':'string','admin_code':'string'})
  package=model_package.load_scope_package(cp0.IPCCH_PACKAGE,scope)
  contract=package['contract']; cols=package['feature_columns']; stats=package['metadata']['imputation_statistics']
  matrix,cr=feature_contract.apply_feature_contract(monthly,contract,cols,package_root=package['scope_dir'],metadata=package['metadata'])
  r={'rows':[len(replay),len(saved)],'saved_sha256':sha(saved_path),'columns':{},'identity':{},'contract_categories':contract['category'].value_counts().to_dict(),'feature_count':len(cols),'contract_rows':len(contract),'contract_order_matches_model':contract['feature_name'].tolist()==cols,'missing_source_columns':[], 'final_missing_shape':list(result['final_missing'].shape),'missing_cells':int(result['final_missing'].to_numpy().sum()),'missing_features':int(result['final_missing'].any(axis=0).sum()),'final_missing_errors':[], 'rule_errors':[], 'dependency_errors':[], 'uncertainty_columns':[c for c in replay if 'uncertainty' in c or 'threshold_margin' in c], 'package_sha256':{p.name:sha(p) for p in sorted(package['scope_dir'].iterdir()) if p.is_file()}}
  r['package_hashes_match_cp0']=r['package_sha256']==prior['ipcch']['scopes'][f'{scope}m']['package_sha256']
  assert len(replay)==len(saved)==6227
  for col in ['area_id','admin_code','feature_period','target_period','feature_month','target_month','scope_months','model_package_id','source_input']:
   if col in replay and col in saved:
    n=int((replay[col].astype(str).to_numpy()!=saved[col].astype(str).to_numpy()).sum());r['identity'][col]={'mismatches':n,'replay_unique_first5':replay[col].astype(str).unique().tolist()[:5]}; assert n==0,(scope,col,n)
   else:r['identity'][col]={'available_replay':col in replay,'available_saved':col in saved}
  assert replay['polygon_id'].astype(str).tolist()==replay['area_id'].astype(str).tolist()
  r['polygon_id_equals_area_id']=True
  assert result['final_missing'].index.tolist()==monthly['admin_code'].astype(str).tolist()
  assert result['final_missing'].columns.tolist()==cols
  for _,row in contract.iterrows():
   f=row['feature_name']; src=row['source_column']; key=row['fill_value_or_stat_key']
   missing=monthly[src].isna() if src in monthly else pd.Series(True,index=monthly.index)
   if src not in monthly:r['missing_source_columns'].append(src)
   if not np.array_equal(result['final_missing'][f].to_numpy(),missing.to_numpy()):r['final_missing_errors'].append(f)
   if abs(float(missing.mean())-cr['features'][f]['pre_fill_missing_rate'])>1e-12:r['final_missing_errors'].append(f+':contract_rate')
   if result['rules'].get(f)!=f'{key}={stats[key]!r}':r['rule_errors'].append(f)
   if result['dependencies'].get(f)!=(src,(0,)):r['dependency_errors'].append(f)
   if missing.any() and not np.allclose(matrix.loc[missing,f].to_numpy(dtype=float),float(stats[key]),rtol=0,atol=0,equal_nan=True):r['rule_errors'].append(f+':actual_fill')
  assert not r['final_missing_errors'] and not r['rule_errors'] and not r['dependency_errors']
  r['postfill_nonfinite_cells']=int((~np.isfinite(matrix.to_numpy(dtype=float))).sum())
  for phase in (2,3,4,5):
   name=f'phase{phase}_worse_score'; a=replay[name].to_numpy(dtype=float);b=saved[name].to_numpy(dtype=float); exact=np.abs(a-b)<=cp0.ATOL; clipped=(a<0)&(b==0); unexplained=~exact&~clipped
   r['columns'][name]={'mismatches':int((~exact).sum()),'negative_to_saved_zero':int((~exact&clipped).sum()),'unexplained':int(unexplained.sum()),'max_abs_diff':float(np.max(np.abs(a-b))), 'max_abs_diff_unexplained':float(np.max(np.abs(a-b)[unexplained])) if unexplained.any() else 0.0,'raw_negative_count':int((a<0).sum())}
   assert not unexplained.any(),(scope,name,r['columns'][name])
   if phase in (2,3):assert exact.all(),(scope,name)
   report['total_clipping'][str(phase)]+=int((~exact&clipped).sum())
   pred=f'phase{phase}_worse_pred'; n=int((replay[pred].to_numpy(dtype=int)!=saved[pred].to_numpy(dtype=int)).sum()); r['columns'][pred]={'mismatches':n};assert n==0,(scope,pred,n)
  n=int((replay['overall_phase_pred'].to_numpy(dtype=int)!=saved['overall_phase_pred'].to_numpy(dtype=int)).sum());r['columns']['overall_phase_pred']={'mismatches':n};assert n==0,(scope,'overall_phase_pred',n)
  r['clipping_counts_match_cp0']=all(r['columns'][f'phase{phase}_worse_score']['negative_to_saved_zero']==prior['ipcch']['scopes'][f'{scope}m']['columns'][f'phase{phase}_worse_score']['explained_by_saved_zero_clip'] for phase in (2,3,4,5))
  assert r['package_hashes_match_cp0'] and r['clipping_counts_match_cp0']
  report['scopes'][str(scope)]=r
  print('SCOPE '+str(scope)+' '+json.dumps({k:r[k] for k in ['rows','missing_cells','missing_features','contract_categories','package_hashes_match_cp0','clipping_counts_match_cp0','columns']},sort_keys=True),flush=True)
 assert report['total_clipping']=={'2':0,'3':0,'4':85,'5':8013},report['total_clipping']
 report['status']='passed'
except Exception as exc:
 report['status']='failed';report['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()});traceback.print_exc()
finally:
 report['source_sha256_after']={str(p.relative_to(REPO)):sha(p) for p in source_paths};report['source_unchanged']=report['source_sha256_before']==report['source_sha256_after'];report['elapsed_seconds']=time.time()-report['started_epoch'];report['script_sha256']=sha('/tmp/cp3_ipcch_wrapper_replay.py')
 if not report['source_unchanged']:report['errors'].append({'type':'SourceChanged','message':'Source modified during verification'});report['status']='failed'
 Path('/tmp/cp3_ipcch_wrapper_report.json').write_text(json.dumps(report,indent=2,sort_keys=True))
 print(json.dumps({'status':report['status'],'source_unchanged':report['source_unchanged'],'elapsed_seconds':report['elapsed_seconds'],'total_clipping':report.get('total_clipping'),'errors':report['errors']},sort_keys=True),flush=True)
sys.exit(0 if report['status']=='passed' else 1)
