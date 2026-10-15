from flask import Flask
import os
import threading
import time
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is alive on Render!'

# Self-ping so Render free tier never sleeps
def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return  # running locally, no ping needed
    while True:
        try:
            requests.get(url, timeout=10)
        except Exception:
            pass
        time.sleep(600)  # ping every 10 minutes
