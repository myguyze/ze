def test_public_api_imports() -> None:
    from ze_proactive.job import ProactiveJob, proactive_job
    from ze_proactive.notifier import ProactiveNotifier
    from ze_proactive.scheduler import ProactiveScheduler

    assert ProactiveJob is not None
    assert callable(proactive_job)
    assert ProactiveNotifier is not None
    assert ProactiveScheduler is not None
