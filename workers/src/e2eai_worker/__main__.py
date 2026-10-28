"""`e2eai-worker`: the background worker (PRD T1, FR-F20).

One task at a time (`--pool=solo`): Docling already uses every CPU core, and the solo pool is the one Celery pool that
works the same on Windows, macOS and Linux. Run it in the worker environment, which holds Docling and PyTorch:

    UV_PROJECT_ENVIRONMENT=<dir outside the repo> uv sync --project workers
    UV_PROJECT_ENVIRONMENT=<same dir> uv run --project workers e2eai-worker
"""

import logging
import sys

log = logging.getLogger("e2eai.worker")


def worker_args(extra: list[str] | None = None) -> list[str]:
    return ["worker", "--pool=solo", "--concurrency=1", "--loglevel=INFO", "--hostname=worker@%h", *(extra or [])]


def main(argv: list[str] | None = None) -> None:
    from celery.signals import worker_ready

    from e2eai.celery_app import get_celery_app

    @worker_ready.connect
    def _warm_up(**_: object) -> None:
        """Load the layout / table / OCR models now, so the first document does not pay for it."""
        try:
            from e2eai.docling_runtime import converter

            converter()
            log.info("document parser ready")
        except Exception as exc:  # noqa: BLE001 - a failed warm-up must not stop the worker; the first parse reports it
            log.warning("document parser warm-up failed: %s", type(exc).__name__)

    get_celery_app().worker_main(worker_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    main()
