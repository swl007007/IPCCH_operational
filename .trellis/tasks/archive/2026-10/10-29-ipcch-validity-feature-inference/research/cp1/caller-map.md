# CP1 research caller map (GitNexus does not index food-crisis-research; direct grep mapping instead)

Worktree: /home/swl007007/projects/food-crisis-research/control-plane-h2h8h14 (branch task/ipcch-h2-h8-h14-final, baseline 4cb493f).
Command: `grep -rnE --include=*.py "[^_a-zA-Z]<symbol>\(" research_cloud | grep -v "def <symbol>(" | grep -v /tests/` per changed symbol (raw output below).

Compatibility summary:
- Every new parameter defaults to the previous behaviour: `oracle=True`, `gpp_availability=False`, `ch_links=False`, Schedule `main_window=True` (and it is not recorded in `record()` when True).
- `check_horizon` keeps 0/6/12 valid with oracle columns. It refuses 2/8/14 with oracle and 0/6/12 without, so no legacy caller can reach a final horizon by accident.
- External callers using defaults: `ipcch_direct_fourclass` (build_dataset, expected_features, oracle_completeness, select_arm), `images/selfcheck.py` (check_config on committed recipes), `ipcch_hpt_control` (check_config on HPT recipes). Their suites are added to the regression run.
- The final arm route is `check_config -> check_final_config`, `prepare -> final_prepare -> vf.build_dataset(oracle=False, gpp_availability=True, ch_links=True)`, `fit -> final_fit -> run_contexts (oracle_completeness oracle=False)`, `plan_main/gate_main` (FINAL_ARM accepted; recipe required). Legacy lookups `PROVIDER_FIRST[h]`, `Schedule.first(h)`, `MAIN_FIRST`, `FINAL_ROWS`, `GPP_BASELINE_RUNS`, `ACLED_BASELINE_RUNS` and `EXPECTED_FEATURES[h]` are not reached on this route: providers are off, there is no main window, the baseline is self_consistency, and the width is the full order.
- `dataset_input.ALL_LABEL_ARMS` gains FINAL_ARM, kept equal to `vp.ARMS - {original}` as asserted by test_training_validity_integration. CH-link tags are added for FINAL_ARM (`CH_LINK_ARMS`); 10-28 ch_correction tags and their order are unchanged.
- The immutable source `R/sources/Food_Crisis_Cluster/.../compact.py` (sha256 82423316…) is not modified. On the validity path no caller of its horizon-validated functions (`label_cutoff`, `build_safe_history`, `build_idp_features`, `validate_horizon`) exists; `monthly_block` takes any horizon list.

## Raw grep output
```
## base_features
  research_cloud/training/ipcch_validity_features.py:1352:    A, order, rows = base_features(sources, labels, countries, horizon)
  research_cloud/training/ipcch_validity_features.py:1353:    B, _, _ = base_features(alt, labels, countries, horizon)
  research_cloud/training/ipcch_validity_features.py:1455:        X, order, rows = base_features(sources, labels, countries, h, oracle=oracle, gpp_availability=gpp_availa
## build_dataset
  research_cloud/training/ipcch_validity_pooled.py:1886:    built = vf.build_dataset(inputs, out.path("dataset"), horizons=(h, *STACK[h]) if hstack else (h,),
  research_cloud/training/ipcch_validity_pooled.py:2597:    built = vf.build_dataset(inputs, out.path("dataset" if formal else "inputs/selection-build/dataset"), horizons
  research_cloud/training/ipcch_validity_pooled.py:3238:    built = vf.build_dataset(inputs, out.path("dataset"), horizons=(h,), matrix_dir=out.path("gcs-only/dataset"), 
  research_cloud/training/ipcch_validity_features.py:1569:    summary = build_dataset(inputs, args.out, horizons, idp_local=args.idp_local, acled_agg=args.acled_agg,
  research_cloud/training/ipcch_direct_fourclass.py:541:    built = vf.build_dataset(inputs, out.path("dataset"), horizons=(horizon,), matrix_dir=out.path("gcs-only/datas
## feature_order
  research_cloud/packages/build_fews_ordinary.py:17:    names, schema_sha, features_sha = fews_ordinary.feature_order()
  research_cloud/packages/build_fews_map.py:17:    schema = fews_ordinary.feature_order()
  research_cloud/training/ipcch_validity_features.py:1202:    order = feature_order(sources["frozen"], sources["ae_names"], h, idp_local=local is not None, acled_agg=acle
## expected_features
  research_cloud/training/ipcch_validity_pooled.py:1010:    check("width", int(n != vf.expected_features(d.horizon, idp_local=True, acled_agg=True)), [n])
  research_cloud/training/ipcch_validity_pooled.py:1282:    want = HSTACK_FEATURES[horizon] if arm == HSTACK_ARM else vf.expected_features(horizon, idp_local=arm in IDP_A
  research_cloud/training/ipcch_validity_pooled.py:1350:    return vf.expected_features(horizon, idp_local=True) if arm == HSTACK_ARM else vf.EXPECTED_FEATURES[int(horizo
  research_cloud/training/ipcch_validity_pooled.py:1940:            n_own = vf.expected_features(h, idp_local=True)
  research_cloud/training/ipcch_validity_pooled.py:2126:    if config.get("n_features") != vf.expected_features(horizon, idp_local=True, acled_agg=True) or "region" in co
  research_cloud/training/ipcch_validity_pooled.py:2127:        raise ValidityError(f"recipe n_features must be {vf.expected_features(horizon, idp_local=True, acled_agg=T
  research_cloud/training/ipcch_validity_pooled.py:3138:    want = vf.expected_features(h, idp_local=True, acled_agg=True, oracle=False)
  research_cloud/training/ipcch_validity_features.py:884:    want = expected_features(horizon, idp_local, acled_agg, oracle)
  research_cloud/training/ipcch_direct_fourclass.py:183:    if config.get("n_features") != vf.expected_features(horizon, idp_local=True):
  research_cloud/training/ipcch_direct_fourclass.py:184:        raise DirectError(f"recipe n_features must be {vf.expected_features(horizon, idp_local=True)} at H{horizon
## oracle_names
  research_cloud/training/ipcch_validity_pooled.py:1894:            if len(names) != 243 + len(vf.oracle_names(k)):
  research_cloud/training/ipcch_validity_features.py:877:    order = list(frozen) + list(ae_names) + oracle_names(horizon, oracle)
  research_cloud/training/ipcch_validity_features.py:1238:    names = oracle_names(horizon, oracle)
  research_cloud/training/ipcch_validity_features.py:1301:    names = oracle_names(horizon)
## oracle_completeness
  research_cloud/training/ipcch_validity_pooled.py:1530:        nf, comp = vf.oracle_completeness(d.X[p["score"]], d.order, d.horizon, oracle=d.arm != FINAL_ARM)
  research_cloud/training/ipcch_validity_features.py:1299:    n_finite, complete = oracle_completeness(X, order, horizon)
  research_cloud/training/ipcch_direct_fourclass.py:481:        nf, comp = vf.oracle_completeness(d.X[score], d.order, d.horizon)
## schedule_from_config
  research_cloud/training/ipcch_validity_pooled.py:1295:        s = schedule_from_config(config, horizon)
  research_cloud/training/ipcch_validity_pooled.py:1874:        schedule = schedule_from_config(config, h)
  research_cloud/training/ipcch_validity_pooled.py:2128:    s = schedule_from_config(config, horizon)
  research_cloud/training/ipcch_validity_pooled.py:3141:    s = schedule_from_config(config, h)
  research_cloud/training/ipcch_validity_pooled.py:3453:        schedule = schedule_from_config(config, a.horizon)
## scoring_blocks
  research_cloud/training/ipcch_validity_pooled.py:412:    last = max(b.cutoff for b in scoring_blocks(h, s))
  research_cloud/training/ipcch_validity_pooled.py:537:    blocks = scoring_blocks(d.horizon, s)
  research_cloud/training/ipcch_validity_pooled.py:2052:    for E in scoring_blocks(d.horizon, d.schedule):
  research_cloud/training/ipcch_validity_pooled.py:2387:    blocks = scoring_blocks(h, schedule)
  research_cloud/training/ipcch_validity_pooled.py:2455:    for b in scoring_blocks(horizon, schedule):
## check_config
  research_cloud/images/selfcheck.py:90:            vp.check_config(json.load(open(os.path.join(root, "training", "recipes", "ipcch-validity-pooled",
  research_cloud/training/ipcch_validity_pooled.py:1873:        check_config(config, h, arm)
  research_cloud/training/ipcch_validity_pooled.py:3452:        check_config(config, a.horizon, a.arm)
  research_cloud/training/ipcch_hpt_control.py:573:            vp.check_config(r, h, vp.HPT_ARM)
  research_cloud/training/ipcch_hpt_control.py:967:        vp.check_config(search, h, vp.HPT_ARM)
  research_cloud/training/ipcch_direct_fourclass.py:581:        check_config(config, h, mode)
## prepare
  research_cloud/service/start.py:173:        env, argv, status = prepare(dict(os.environ))
  research_cloud/training/ipcch_validity_pooled.py:3116:    prep = prepare(inputs, config, out, manifest)
  research_cloud/training/ipcch_validity_pooled.py:3322:    prep = prepare(inputs, config, out, manifest)
  research_cloud/training/ipcch_validity_pooled.py:3362:    prep = prepare(inputs, config, out, manifest)
  research_cloud/training/ipcch_validity_pooled.py:3517:        prep = prepare(inputs, config, out, manifest)
  research_cloud/training/ipcch_hpt_control.py:897:        result = {"prepare": lambda: prepare(ctx), "export": lambda: export(ctx, a.horizon), "freeze": lambda: freeze(c
## fit
  research_cloud/training/ipcch_validity_pooled.py:1107:        model.fit(X, Y[:, k], sample_weight=w, verbose=False)
  research_cloud/training/ipcch_validity_pooled.py:1182:    T = cr.Transform.fit(P, Z, w)
  research_cloud/training/common.py:503:        result = fit(inputs, manifest, config, params, out)
## select_arm
  research_cloud/training/ipcch_validity_pooled.py:1898:        labels, X = select_arm(objs["labels"], Xs, arm)
  research_cloud/training/ipcch_validity_pooled.py:1901:        labels, X = select_arm(objs["labels"], objs["horizons"][h]["X"], arm)
  research_cloud/training/ipcch_validity_pooled.py:2601:    labels, X = select_arm(objs["labels"], objs["horizons"][h]["X"], HPT_ARM)
  research_cloud/training/ipcch_validity_pooled.py:3241:    labels, X = select_arm(objs["labels"], objs["horizons"][h]["X"], FINAL_ARM)
  research_cloud/training/ipcch_validity_pooled.py:3472:    L, Xa = select_arm(labels, X, a.arm)
  research_cloud/training/ipcch_direct_fourclass.py:535:    La, Xa = vp.select_arm(labels, X, ARM)
  research_cloud/training/ipcch_direct_fourclass.py:544:    labels, X = vp.select_arm(objs["labels"], objs["horizons"][horizon]["X"], ARM)
```
