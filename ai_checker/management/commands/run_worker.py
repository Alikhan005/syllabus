import time
import logging
import os
from django.core.management.base import BaseCommand
from syllabi.models import Syllabus
from ai_checker.llm import warmup_llm
from ai_checker.services import run_ai_check
from workflow.services import change_status_system

# Настраиваем логирование
logger = logging.getLogger(__name__)
IDLE_SLEEP_SECONDS = max(0.2, float(os.getenv("AI_WORKER_IDLE_SLEEP", "1.0")))
PRELOAD_MODEL = os.getenv("AI_WORKER_PRELOAD_MODEL", "true").strip().lower() in {"1", "true", "yes", "on"}

class Command(BaseCommand):
    help = 'Запускает фоновый процесс проверки силлабусов через ИИ'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Воркер запущен! Ожидание задач... (Нажми Ctrl+C, чтобы остановить)'))
        if PRELOAD_MODEL:
            try:
                model_name = warmup_llm()
                self.stdout.write(self.style.SUCCESS(f'LLM ready: {model_name}'))
            except Exception as exc:
                logger.warning("LLM preload failed, continuing without preload: %s", exc)
                self.stdout.write(self.style.WARNING(f'LLM preload failed: {exc}'))
        
        try:
            while True:
                # 1. Ищем силлабус со статусом "На проверке ИИ"
                # order_by('updated_at') берет самый старый из очереди (FIFO)
                syllabus = Syllabus.objects.filter(status=Syllabus.Status.AI_CHECK).order_by('updated_at').first()
                
                if syllabus:
                    self.stdout.write(self.style.WARNING(f'Найден силлабус ID {syllabus.id}. Начинаю проверку...'))
                    
                    try:
                        # 2. Запускаем "умную" проверку (код из services.py)
                        result_record = run_ai_check(syllabus)
                        
                        # 3. Анализируем результат
                        raw_data = result_record.raw_result or {}
                        is_approved = raw_data.get('approved', False)
                        # feedback = raw_data.get('feedback', '') # Можно использовать, если нужно логировать детали
                        
                        if is_approved:
                            # Если ИИ одобрил -> Отправляем Декану
                            change_status_system(
                                syllabus,
                                Syllabus.Status.REVIEW_DEAN,
                                comment="Автоматическая проверка ИИ пройдена.",
                                ai_feedback=syllabus.ai_feedback,
                            )
                            self.stdout.write(self.style.SUCCESS(f'Силлабус {syllabus.id}: Успех -> Декану'))
                        else:
                            # Если нашел ошибки -> Возвращаем преподавателю
                            change_status_system(
                                syllabus,
                                Syllabus.Status.CORRECTION,
                                comment="Силлабус возвращен после автоматической проверки ИИ.",
                                ai_feedback=syllabus.ai_feedback,
                            )
                            self.stdout.write(self.style.ERROR(f'Силлабус {syllabus.id}: Найдены ошибки -> На доработку'))

                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Ошибка при обработке ID {syllabus.id}: {e}'))
                        # Чтобы не зациклиться на ошибке, переводим в статус коррекции
                        failure_feedback = f"Критическая ошибка проверки: {e}"
                        try:
                            change_status_system(
                                syllabus,
                                Syllabus.Status.CORRECTION,
                                comment="Автоматическая проверка завершилась с критической ошибкой.",
                                ai_feedback=failure_feedback,
                            )
                        except Exception:
                            # Fallback: never keep item stuck in AI_CHECK.
                            syllabus.status = Syllabus.Status.CORRECTION
                            syllabus.ai_feedback = failure_feedback
                            syllabus.save(update_fields=["status", "ai_feedback"])
                
                else:
                    # Если задач нет, спим 5 секунд, чтобы не грузить процессор
                    # Keep queue latency low while avoiding busy-loop.
                    time.sleep(IDLE_SLEEP_SECONDS)

        except KeyboardInterrupt:
            # Ловим нажатие Ctrl+C и выходим красиво
            self.stdout.write(self.style.SUCCESS('\nВоркер остановлен пользователем. До встречи!'))
