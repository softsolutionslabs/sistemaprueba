"""
WSGI config for ecommerce_core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_core.settings')

application = get_wsgi_application()

# Whitenoise for static files - ESSENTIAL FOR RAILWAY
from whitenoise import WhiteNoise

# Serve static files through Whitenoise
application = WhiteNoise(
    application, 
    root=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'staticfiles')
)

# Optional: Add additional directories if needed
# application.add_files('/path/to/more/static/files', prefix='more-files/')