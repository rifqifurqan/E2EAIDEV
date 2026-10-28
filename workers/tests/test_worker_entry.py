"""The worker starts Celery with the safe, portable settings (no broker needed: the app is faked)."""

from e2eai_worker import __main__ as entry


def test_the_worker_runs_one_task_at_a_time_in_the_solo_pool():
    args = entry.worker_args()
    assert args[0] == "worker"  # Celery's worker_main requires the sub-command first
    assert "--pool=solo" in args and "--concurrency=1" in args


def test_extra_command_line_arguments_are_passed_through():
    assert entry.worker_args(["--loglevel=DEBUG"])[-1] == "--loglevel=DEBUG"


def test_main_hands_the_arguments_to_the_celery_app(monkeypatch):
    seen = {}

    class _App:
        def worker_main(self, argv):
            seen["argv"] = argv

    import e2eai.celery_app as celery_module

    monkeypatch.setattr(celery_module, "get_celery_app", lambda: _App())
    entry.main(["--queues=celery"])
    assert seen["argv"][0] == "worker" and seen["argv"][-1] == "--queues=celery"
