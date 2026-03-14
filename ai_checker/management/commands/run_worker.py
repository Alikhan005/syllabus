import logging
import os
import time
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

from ai_checker.llm import warmup_llm
from ai_checker.services import run_ai_check
from syllabi.models import Syllabus
from workflow.services import change_status_system


logger = logging.getLogger(__name__)
IDLE_SLEEP_SECONDS = max(0.2, float(os.getenv("AI_WORKER_IDLE_SLEEP", "1.0")))
WORKER_LOCK_PATH = Path(__file__).resolve().parents[3] / ".run_worker.lock"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PRELOAD_MODEL = _env_bool("AI_WORKER_PRELOAD_MODEL", False)
WORKER_VERBOSE = _env_bool("AI_WORKER_VERBOSE", True)


class Command(BaseCommand):
    help = "Run background AI syllabus checks."

    def _acquire_worker_lock(self):
        WORKER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = open(WORKER_LOCK_PATH, "a+")
        try:
            lock_handle.seek(0)
            lock_handle.write("0")
            lock_handle.flush()
            lock_handle.seek(0)

            if os.name == "nt" and msvcrt is not None:
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
            elif fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            lock_handle.seek(0)
            lock_handle.truncate()
            lock_handle.write(str(os.getpid()))
            lock_handle.flush()
            return lock_handle
        except OSError:
            lock_handle.close()
            return None

    def _release_worker_lock(self, lock_handle):
        if not lock_handle:
            return
        try:
            lock_handle.seek(0)
            if os.name == "nt" and msvcrt is not None:
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            lock_handle.close()

    def _syllabus_table_ready(self):
        try:
            return "syllabi_syllabus" in connection.introspection.table_names()
        except (OperationalError, ProgrammingError):
            return False

    def _report_missing_table(self):
        db_name = connection.settings_dict.get("NAME", "")
        db_host = connection.settings_dict.get("HOST", "")
        db_port = connection.settings_dict.get("PORT", "")
        db_user = connection.settings_dict.get("USER", "")
        self.stdout.write(
            self.style.ERROR(
                f'Table "syllabi_syllabus" is missing in database "{db_name}" '
                f'on {db_host}:{db_port} as user "{db_user}". '
                'Run "python manage.py migrate" for this database.'
            )
        )

    def handle(self, *args, **options):
        lock_handle = self._acquire_worker_lock()
        if lock_handle is None:
            self.stdout.write(
                self.style.WARNING(
                    "Another run_worker process is already active. Stop the old worker before starting a new one."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Worker started. Waiting for tasks... Press Ctrl+C to stop."
            )
        )

        if PRELOAD_MODEL:
            try:
                model_name = warmup_llm()
                self.stdout.write(self.style.SUCCESS(f"LLM ready: {model_name}"))
            except Exception as exc:
                logger.warning("LLM preload failed, continuing without preload: %s", exc)
                if WORKER_VERBOSE:
                    self.stdout.write(self.style.WARNING(f"LLM preload failed: {exc}"))
                else:
                    self.stdout.write(self.style.WARNING("LLM preload skipped."))

        missing_table_reported = False

        try:
            while True:
                if not self._syllabus_table_ready():
                    if not missing_table_reported:
                        self._report_missing_table()
                        missing_table_reported = True
                    time.sleep(IDLE_SLEEP_SECONDS)
                    continue

                missing_table_reported = False

                try:
                    syllabus = (
                        Syllabus.objects.filter(status=Syllabus.Status.AI_CHECK)
                        .order_by("updated_at")
                        .first()
                    )
                except (OperationalError, ProgrammingError) as exc:
                    error_text = str(exc).lower()
                    if (
                        "syllabi_syllabus" in error_text
                        or "does not exist" in error_text
                        or "не существует" in error_text
                    ):
                        self._report_missing_table()
                        missing_table_reported = True
                        time.sleep(IDLE_SLEEP_SECONDS)
                        continue
                    raise

                if not syllabus:
                    time.sleep(IDLE_SLEEP_SECONDS)
                    continue

                self.stdout.write(
                    self.style.WARNING(
                        f"Found syllabus ID {syllabus.id}. Starting AI check..."
                    )
                )

                try:
                    result_record = run_ai_check(syllabus)
                    raw_data = result_record.raw_result or {}
                    is_approved = raw_data.get("approved", False)

                    if is_approved:
                        change_status_system(
                            syllabus,
                            Syllabus.Status.REVIEW_DEAN,
                            comment="Automatic AI review passed.",
                            ai_feedback=syllabus.ai_feedback,
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Syllabus {syllabus.id}: passed and sent to dean review."
                            )
                        )
                    else:
                        change_status_system(
                            syllabus,
                            Syllabus.Status.CORRECTION,
                            comment="Returned after automatic AI review.",
                            ai_feedback=syllabus.ai_feedback,
                        )
                        self.stdout.write(
                            self.style.ERROR(
                                f"Syllabus {syllabus.id}: issues found, returned for correction."
                            )
                        )

                except Exception as exc:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error while processing syllabus {syllabus.id}: {exc}"
                        )
                    )
                    failure_feedback = f"Critical AI review error: {exc}"
                    try:
                        change_status_system(
                            syllabus,
                            Syllabus.Status.CORRECTION,
                            comment="Automatic AI review failed with a critical error.",
                            ai_feedback=failure_feedback,
                        )
                    except Exception:
                        syllabus.status = Syllabus.Status.CORRECTION
                        syllabus.ai_feedback = failure_feedback
                        syllabus.save(update_fields=["status", "ai_feedback"])

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\nWorker stopped."))
        finally:
            self._release_worker_lock(lock_handle)
