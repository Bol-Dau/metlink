import os
from datetime import date, datetime
from decimal import Decimal

from database.connector import _load_dotenv_if_present, check_connection_health
_load_dotenv_if_present()

from flask import Flask, jsonify
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
    app = Flask(__name__)
    app.json = CustomJSONProvider(app)

    # Allow frontend requests during local development
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register API blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ussd_bp)

    @app.get("/api/health")
    def health_check():
        db_ok = check_connection_health()
        status_code = 200 if db_ok else 503
        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "database": "connected" if db_ok else "unreachable",
        }), status_code

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
