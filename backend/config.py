"""Deployment settings; local development remains the default."""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = os.getenv('WATCHMYWORK_PRODUCTION') == '1'
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', '').rstrip('/')
if not PUBLIC_ORIGIN and PRODUCTION and os.getenv('RAILWAY_PUBLIC_DOMAIN'):
    PUBLIC_ORIGIN = 'https://' + os.environ['RAILWAY_PUBLIC_DOMAIN']
if PUBLIC_ORIGIN:
    parsed = urlsplit(PUBLIC_ORIGIN)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query
            or parsed.fragment or parsed.username or parsed.password or parsed.port
            or not re.fullmatch(r'[a-zA-Z0-9.-]+', parsed.hostname)):
        raise ValueError('PUBLIC_ORIGIN must be an exact HTTPS origin without a path or port')

# Before Railway assigns a domain, health/static pages can start. Automation
# becomes available after the public origin is configured and the service restarts.
DEMO_ORIGIN = PUBLIC_ORIGIN if PRODUCTION else 'http://127.0.0.1:5173'
WEATHER_URL = DEMO_ORIGIN + ('/weather' if PRODUCTION else '/')
DEVELOPER_URL = DEMO_ORIGIN + '/developer'
FRONTEND_DIST = ROOT / 'frontend' / 'dist'
DEMO_DIST = ROOT / 'mock-site' / 'dist'
