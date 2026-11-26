"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

from django.core.wsgi import get_wsgi_application

from config import env

# `.env` is the only source of configuration, including DJANGO_SETTINGS_MODULE.
env.load()

application = get_wsgi_application()
