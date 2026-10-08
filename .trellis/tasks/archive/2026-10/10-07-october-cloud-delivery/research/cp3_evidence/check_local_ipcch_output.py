"""Independent lightweight checks on actual IPCCH October integration output."""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

repo, root = map(Path, sys.argv[1:3])
v3 = repo / 'Outcome/model_delivery/202609_h5/20260923_country_confidence_v3'
template = pd.read_csv(v3 / 'inputs/ipcch_april_panel.csv', dtype={'area_id': str, 'admin_code': str})
census = pd.read_csv(v3 / 'ipcch/country_population_reference.csv', dtype=str)
lookup = template[['area_id', 'country']].merge(census[['country', 'ISO3']], on='country', validate='many_to_one')
assert len(lookup) == len(template) and not lookup['area_id'].duplicated().any()
expected_ids = set(template.area_id)
report = {'kind': 'full-roster IPCCH integration with bounded smoke remote inputs; not latest-data acceptance',
          'output': str(root), 'scopes': {}, 'checks': [], 'outputs': {}}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def header(path):
    with path.open(newline='') as f:
        return next(csv.reader(f))

def phase(values):
    return max([1] + [j + 2 for j, value in enumerate(values) if value >= .2])

for horizon, target in ((0, '2026-10'), (6, '2027-04'), (12, '2027-10')):
    directory = root / f'scopes/{horizon}m/ipcch'
    names = ('polygon_predictions', 'country_predictions', 'polygon_model_mapping',
             'polygon_training_errors', 'country_confidence')
    tables = {}
    for name in names:
        path = directory / (name + '.csv')
        assert header(path) == header(v3 / 'ipcch' / path.name), (horizon, name, 'header')
        tables[name] = pd.read_csv(path, dtype={'polygon_id': str, 'area_id': str, 'admin_code': str, 'ISO3': str})
        report['outputs'][str(path.relative_to(root))] = digest(path)
    prediction = tables['polygon_predictions']
    assert set(prediction.area_id) == expected_ids and len(prediction) == len(expected_ids)
    assert prediction.area_id.equals(prediction.polygon_id)
    assert set(prediction.feature_period) == {'2026-10'} and set(prediction.target_period) == {target}
    assert set(prediction.scope_months) == {horizon}
    old = template.set_index('area_id').loc[prediction.area_id]
    assert prediction.admin_code.tolist() == old.admin_code.tolist()
    np.testing.assert_allclose(prediction.population_estimate, old.population_estimate, rtol=0, atol=0)
    assert prediction.population_reference_period.tolist() == old.population_reference_period.tolist()
    assert all(method == ('observed_feature_month' if month == '2026-10' else 'last_observation_carried_forward')
               for month, method in zip(prediction.population_reference_period, prediction.population_imputation_method))
    scores = prediction[[f'phase{j}_worse_score' for j in range(2, 6)]].to_numpy()
    assert np.isfinite(scores).all()
    assert np.array_equal([phase(row) for row in scores], prediction.overall_phase_pred)
    joined = prediction.merge(lookup, on='area_id', validate='one_to_one')
    country = tables['country_predictions'].set_index('ISO3')
    confidence = tables['country_confidence'].set_index('ISO3')
    assert set(country.index) == set(census.ISO3) == set(confidence.index)
    assert not country.index.duplicated().any() and not confidence.index.duplicated().any()
    max_diff = 0.
    for iso, group in joined.groupby('ISO3', sort=True):
        weights = group.population_estimate.to_numpy()
        assert np.isfinite(weights).all() and (weights >= 0).all() and weights.sum() > 0
        means = []
        for j in range(2, 6):
            name = f'phase{j}_worse_score'
            values = group[name].to_numpy()
            mean = math.fsum(float(w) * float(v) for w, v in zip(weights, values)) / math.fsum(weights)
            sd = math.sqrt(math.fsum(float(w) * (float(v) - mean)**2 for w, v in zip(weights, values)) / math.fsum(weights))
            np.testing.assert_allclose([country.loc[iso, name], country.loc[iso, name + '_area_dispersion']],
                                       [mean, sd], rtol=0, atol=1e-12)
            max_diff = max(max_diff, abs(country.loc[iso, name] - mean))
            means.append(mean)
        assert confidence.loc[iso, 'country_overall_phase'] == phase(means)
        assert confidence.loc[iso, 'country_maximum_phase'] == group.overall_phase_pred.max()
    diagnostics = tables['polygon_training_errors']
    assert set(diagnostics.polygon_id) == expected_ids and len(diagnostics) == len(expected_ids)
    assert diagnostics[['training_sample_count', 'training_error_count', 'training_error_rate']].isna().all().all()
    current = {'country_overall_phase', 'country_overall_phase_availability', 'country_overall_phase_method', 'country_maximum_phase'}
    assert confidence[[c for c in confidence if c not in current]].isna().all().all()
    mapping = tables['polygon_model_mapping']
    assert set(mapping.polygon_id) == expected_ids and len(mapping) == len(expected_ids)
    assert set(mapping.horizon_months) == {horizon} and set(mapping.target_month) == {target}
    report['scopes'][str(horizon)] = {'rows': len(prediction), 'countries': len(country),
         'country_score_max_abs_diff': max_diff, 'unclipped_score_cells_below_zero': int((scores < 0).sum()),
         'unclipped_score_cells_above_one': int((scores > 1).sum())}

availability = pd.read_csv(root / 'reports/ipcch_diagnostic_availability.csv', dtype=str)
assert set(availability.status) == {'unavailable'} and set(availability.reason) == {'missing_evidence'}
assert availability.evidence_ref.isna().all() and set(availability.horizon_months) == {'0', '6', '12'}
report['availability_rows'] = len(availability)
for name in ('country_population_reference.csv', 'polygons.geojson'):
    assert digest(root / 'ipcch' / name) == digest(v3 / 'ipcch' / name), name
    report['outputs']['ipcch/' + name] = digest(root / 'ipcch' / name)
report['checks'] = ['15 scope table schemas', 'full native roster and fixed O/targets', 'unchanged population observations and correct carry methods',
                    'raw score phase cascade', 'independent country mean and SD within 1e-12',
                    'country maximum including zero-weight areas', 'blank diagnostics and explicit unavailable sidecar']
report['status'] = 'passed'
print(json.dumps(report, indent=2, allow_nan=False))
