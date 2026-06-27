from cloud.common.runtime_config import RuntimeDefaults, resolve_runtime_config


def test_default_timeouts_and_retry_policy():
    config = resolve_runtime_config({})

    assert config == RuntimeDefaults(
        gee_poll_interval_seconds=60,
        gee_export_timeout_seconds=21600,
        batch_job_timeout_seconds=28800,
        vertex_ai_custom_job_timeout_seconds=7200,
        max_retries=2,
    )


def test_manifest_deployment_can_override_defaults():
    config = resolve_runtime_config(
        {
            "gee_poll_interval_seconds": 30,
            "gee_export_timeout_seconds": 100,
            "batch_job_timeout_seconds": 200,
            "vertex_ai_custom_job_timeout_seconds": 300,
            "retry_policy": {"max_retries": 1},
        }
    )

    assert config.gee_poll_interval_seconds == 30
    assert config.gee_export_timeout_seconds == 100
    assert config.batch_job_timeout_seconds == 200
    assert config.vertex_ai_custom_job_timeout_seconds == 300
    assert config.max_retries == 1
