import os
import sys
from pathlib import Path

# Add project root directory to sys.path so modules can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import Flask app from web_app
from web_app import app

# Vercel Serverless Function entrypoint: exposes `app` as WSGI handler
