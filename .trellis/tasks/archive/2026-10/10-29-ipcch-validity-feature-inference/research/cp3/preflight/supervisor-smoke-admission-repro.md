# Supervisor smoke admission reproduction

2026-10-30; locked fewsnet-test-lock-20261022 Python -B; in-memory resolver only, no real input read. Working validator SHA256: bd7b8891792d0da8e083a546875476d5e2825b6f51e0b4933cb1140d26d9ab6e

Starting from test_delivery_request_v2.request, set mode=smoke, publication=candidate, release namespace=smoke, select inference-only, and retain valid model envelope/runtime references. Set feature_batch.manifest to gs://bucket/ipcch-v2/real/feature_batches/ipcch-2026-10-other-123456789abc/manifest.json with a syntactically valid generation/hash. Resolver records URI calls and returns each supplied hash.

Observed: admit() returns validation_level=admitted and resolver is called on the real feature-batch URI. This confirms validation-before-resolution lacks smoke source admission; later load_batch namespace guard occurs too late. Required regression: whole run_request refuses misrouted batch and refresh refs before any real resolver touch. Explicit shared envelope/runtime metadata handling must not permit real feature/history inputs.

Initial reproduction used invalid one-character GCS bucket and was rejected structurally; corrected valid bucket reproduces the issue. No cloud calls or stores modified.
