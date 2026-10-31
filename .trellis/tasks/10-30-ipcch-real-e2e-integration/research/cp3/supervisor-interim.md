# CP3 Supervisor interim

CP2 accepted/committed as 70f9d10. CP3 is in progress; no gate acceptance yet.

- FEWS preservation interpretation resolved under PRD AC6: preserve the inherited
  member payload including any existing marker; record this run's inheritance
  outside that payload. Inspected narrow publication diff; 9 publication and 11
  release tests reported passed under guard, pending final frozen evidence.
- Submission instant must be captured after input preparation/uploads when the
  complete request is frozen. Provisional preflight time is not persisted. Test
  upload crossing UTC month and lost final-upload response with identical replay.
- Early submit inspection fed back realistic country_reference namespace handling
  (it is not an allowlisted shared reference) and strict keep-field validation
  (do not erase invalid extra fields before the existing validator sees them).
- User confirmed ACLED refresh plus all other ten keep choices. Exact recoverable
  source files/hashes are in ../cp5-local-prerequisites.md; still validate coverage.
- Local Windows Docker client exists, but daemon is unavailable and WSL integration
  disabled. Continue offline build-context/artifact checks; concrete bounded image
  build/verification must be part of CP4's reviewed operation packet if local
  build remains unavailable. No Docker reconfiguration, pull or cloud call now.

## Deployment compatibility finding (open)

Retaining work_dir is correct for the existing baseline, but changing its config's
image later still breaks legacy operations. pipeline.destination/load_initialized
compares the image URI; legacy requests take init.runtime. The deployed workflow
passes its configured image, and delivery_job.prepare_inputs requires exact request
image equality. check_environment/check_acceptance also bind the image/environment.
Existing maintenance apply deploys jobs but does not migrate initialized state;
publish_model permits destination rebinding only with the same runtime digest.

This is distinct from the intentional post-v2 activation block on legacy IPCCH;
FEWS-only is meant to remain supported. Executor is determining the smallest
supported new-image compatibility/acceptance/state transition. Do not bypass guards,
hand-edit initialized state, fabricate acceptance or retrain. No cloud deployment
until the compatibility disposition is concrete. Local source anchors from the
scout: pipeline.py:515-525, 666-720, 1244-1351, 1504-1538; delivery_job.py:148-169,
228-248, 631-674. Exact line numbers may shift with CP3 edits.

Also requested real build_context.sh staging of the accepted payload under the
guard: install_dryrun.py uses symlinks for hashing and is not actual copy/build
evidence. Docker remains unavailable; no image-build success may be claimed.
