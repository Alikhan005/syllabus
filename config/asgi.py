"""
ASGI-конфигурация проекта config.

Открывает ASGI callable как переменную уровня модуля с именем ``application``.

Подробнее об этом файле:
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
