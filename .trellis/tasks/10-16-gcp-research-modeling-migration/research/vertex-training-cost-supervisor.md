# Vertex training reservation inputs — 2026-10-16

Read-only scout checked official public documentation and existing SKU catalog; no project calls or jobs were made. These are quote inputs, not billed amounts or guaranteed spending stops.

## Standard CPU pricing

Official [Vertex pricing](https://cloud.google.com/vertex-ai/pricing), Custom-trained models → Training, lists `n1-standard-4 $0.21849885 / 1 hour` for Iowa. This equals four cores ×0.03635265 plus15GiB ×0.00487255 in saved `scratch/p3/skus/vertex.json` entries1576 and8176 (OnDemand, effective2026-10-15).

The separate management entries6091 and1603 total0.0284989/hour for this machine. The official wording about management fees in addition to infrastructure appears under Spot VMs and Compute Engine reservations. Strong inference: do not add that management amount a second time to the standard Vertex on-demand training price. The earlier0.123498875 compute-only illustration in `cost-inputs-supervisor.md` overcounts this combination.

[HPT overview](https://cloud.google.com/vertex-ai/docs/training/hyperparameter-tuning-overview) says charges are based on the duration of trials initiated by the HPT job. No separate HPT charge was found in the price table; absence is not an explicit guarantee of zero surcharge.

## Time and billing boundaries

- [HPT configuration](https://cloud.google.com/vertex-ai/docs/training/using-hyperparameter-tuning): `trialJobSpec.scheduling.timeout` is the maximum running time **for each trial**. Use900s with maxTrialCount2 and parallelTrialCount1 for the approved smoke.
- [Scheduling reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/Shared.Types/CustomJobSpec): timeout is maximum job running time, default7days. `maxWaitDuration` applies to resource provisioning for FLEX_START (reference text still uses DWS_FLEX_START), not STANDARD CPU.
- [DWS guide](https://cloud.google.com/vertex-ai/docs/training/schedule-jobs-dws) describes supported GPU workloads; do not use its wait bound as a CPU wall-clock guarantee.
- Pricing says training is charged from resource provisioning until job finish, in30second increments, with no minimum usage duration. [Lifecycle](https://cloud.google.com/vertex-ai/docs/training/understanding-training-service) sets RUNNING once workers are available. No official bound was found for all paid startup/container-pull/termination overhead;900s cannot establish the full charged-time ceiling.
- `disableRetries:true` disables internal-error retries after running starts and overrides worker-restart behavior. It is not evidence that all provisioning retries are disabled.

## Conservative reservation arithmetic

Two15minute trials at0.21849885/hour give0.109249425 compute dollars. The official displayed standard-PD hourly price0.000063014/GiB-hour yields0.0031507 for100GiB over the combined half-hour. Baseline total **0.112400125**, before overhead and other CustomJobs.

The saved PD SKU's0.046/GiB-month conversion implies744hours/month and a slightly lower disk estimate; use the higher displayed hourly amount for the reservation, naming that choice.

Reserve explicit startup/termination overhead and round each trial conservatively to30seconds. Keep that assumption distinct from a provider guarantee, retain reservations until verified terminal status, and reconcile other CustomJobs/failed attempts separately. Monthly budget and running timeout alone do not provide a hard billing cap.
