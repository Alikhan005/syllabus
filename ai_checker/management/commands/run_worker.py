import logging
import os
import time
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import Q
from django.db.utils import NotSupportedError, OperationalError, ProgrammingError
from django.utils import timezone

from ai_checker.llm import warmup_llm
from ai_checker.services import run_ai_check
from syllabi.models import Syllabus
from workflow.services import change_status_system


logger = logging.getLogger(__name__)
IDLE_SLEEP_SECONDS = max(0.2, float(os.getenv("AI_WORKER_IDLE_SLEEP", "1.0")))
CLAIM_TTL_SECONDS = max(60.0, float(os.getenv("AI_WORKER_CLAIM_TTL", "900")))
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

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Force-start the worker by removing the existing lock file if it cannot be "
                "resolved automatically."
            ),
        )

    def _worker_identity(self) -> str:
        return f"pid:{os.getpid()}"

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _read_lock_pid(self):
        try:
            raw_pid = WORKER_LOCK_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not raw_pid:
            return None
        try:
            return int(raw_pid)
        except ValueError:
            return None

    def _acquire_worker_lock(self, force: bool = False):
        WORKER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_handle = open(WORKER_LOCK_PATH, "x", encoding="utf-8")
            lock_handle.write(str(os.getpid()))
            lock_handle.flush()
            return lock_handle
        except FileExistsError:
            existing_pid = self._read_lock_pid()
            if existing_pid and existing_pid > 0 and self._is_pid_alive(existing_pid):
                if force:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Run_worker lock belongs to active PID {existing_pid}. "
                            "Force mode cannot safely stop it."
                        )
                    )
                return None

            if force:
                try:
                    with open(WORKER_LOCK_PATH, "w", encoding="utf-8") as existing_handle:
                        existing_handle.write(str(os.getpid()))
                        existing_handle.flush()
                    return open(WORKER_LOCK_PATH, "r", encoding="utf-8")
                except OSError:
                    pass

            try:
                WORKER_LOCK_PATH.unlink()
            except OSError:
                return None
            return self._acquire_worker_lock(force=force)
        except OSError:
            return None

    def _release_worker_lock(self, lock_handle):
        if not lock_handle:
            return
        try:
            lock_handle.close()
        except OSError:
            pass
        finally:
            try:
                lock_pid = self._read_lock_pid()
                if lock_pid == os.getpid():
                    WORKER_LOCK_PATH.unlink(missing_ok=True)
            except OSError:
                pass

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

    def _claim_next_syllabus(self):
        stale_before = timezone.now() - timedelta(seconds=CLAIM_TTL_SECONDS)
        queryset = (
            Syllabus.objects.filter(status=Syllabus.Status.AI_CHECK)
            .filter(Q(ai_claimed_at__isnull=True) | Q(ai_claimed_at__lt=stale_before))
            .order_by("updated_at", "id")
        )

        with transaction.atomic():
            locked_queryset = queryset
            try:
                if connection.features.has_select_for_update:
                    if connection.features.has_select_for_update_skip_locked:
                        locked_queryset = queryset.select_for_update(skip_locked=True)
                    else:
                        locked_queryset = queryset.select_for_update()
            except NotSupportedError:
                locked_queryset = queryset

            syllabus = locked_queryset.first()
            if syllabus is None:
                return None

            syllabus.ai_claimed_at = timezone.now()
            syllabus.ai_claimed_by = self._worker_identity()
            syllabus.save(update_fields=["ai_claimed_at", "ai_claimed_by"])
            return syllabus

    def handle(self, *args, **options):
        force = options.get("force", False)
        lock_handle = self._acquire_worker_lock(force=force)
        if lock_handle is None:
            stale_pid = None
            if WORKER_LOCK_PATH.exists():
                try:
                    stale_pid = int(WORKER_LOCK_PATH.read_text(encoding="utf-8").strip())
                except Exception:
                    stale_pid = None

            self.stdout.write(
                self.style.WARNING(
                    f"Another run_worker process is already active (PID: {stale_pid or 'unknown'}). "
                    "Stop the old worker before starting a new one."
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
                    syllabus = self._claim_next_syllabus()
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
                        f"Claimed syllabus ID {syllabus.id} for AI check."
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
                        syllabus.ai_claimed_at = None
                        syllabus.ai_claimed_by = ""
                        syllabus.save(
                            update_fields=[
                                "status",
                                "ai_feedback",
                                "ai_claimed_at",
                                "ai_claimed_by",
                            ]
                        )

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\nWorker stopped."))
        finally:
            self._release_worker_lock(lock_handle)
