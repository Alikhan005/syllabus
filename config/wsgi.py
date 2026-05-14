"""
WSGI-конфигурация проекта config.

Открывает WSGI callable как переменную уровня модуля с именем ``application``.

Подробнее об этом файле:
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
