"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

from django.core.asgi import get_asgi_application

from config import env

# `.env` is the only source of configuration, including DJANGO_SETTINGS_MODULE.
env.load()

application = get_asgi_application()
