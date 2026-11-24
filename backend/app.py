import os
from datetime import date, datetime
from decimal import Decimal

from database.connector import _load_dotenv_if_present, check_connection_health
_load_dotenv_if_present()

from flask import Flask, jsonify, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from backend.routes.admin_routes import admin_bp
from backend.routes.auth_routes import auth_bp
from backend.routes.ussd_routes import ussd_bp


class CustomJSONProvider(DefaultJSONProvider):
    """Ensure PostgreSQL dates, timestamps, and decimals serialize cleanly to JSON."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def create_app() -> Flask:
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

    app = Flask(__name__)
    app.json = CustomJSONProvider(app)

    cors_origins_raw = os.getenv("CORS_ORIGINS", "").strip()
    if not cors_origins_raw or cors_origins_raw == "*":
        cors_origins = "*"
    else:
        cors_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    @app.get("/")
    def serve_index():
        return send_from_directory(frontend_dir, "index.html")

    @app.get("/api/health")
    def health_check():
        db_ok = check_connection_health()
        status_code = 200 if db_ok else 503
        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "database": "connected" if db_ok else "unreachable",
        }), status_code

    # Register API blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ussd_bp)

    # Serve CSS, JS, images, and other HTML pages from frontend/
    @app.get("/<path:path>")
    def serve_frontend_files(path):
        return send_from_directory(frontend_dir, path)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=True)
