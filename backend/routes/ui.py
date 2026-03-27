"""
backend/routes/ui.py
---------------------
Serves the kiosk frontend HTML page.
"""

from flask import Blueprint, render_template

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def index():
    return render_template("index.html")
