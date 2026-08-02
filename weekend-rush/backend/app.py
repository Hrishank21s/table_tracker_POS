import os

from flask import Flask, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS

from models import TableData, User, db

bcrypt = Bcrypt()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def seed_if_empty():
    if User.query.count() == 0:
        db.session.add(
            User(
                username="admin",
                password_hash=bcrypt.generate_password_hash("admin").decode("utf-8"),
                role="admin",
            )
        )

    if TableData.query.count() == 0:
        table_no = 1
        for floor in (1, 2, 3):
            for _ in range(3):
                db.session.add(
                    TableData(
                        table_no=table_no,
                        floor=floor,
                        status="idle",
                        current_rate=3.0,
                        accumulated_seconds=0,
                    )
                )
                table_no += 1

    db.session.commit()


def create_app(database_uri=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri or os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "weekend_rush.db")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET", "weekend-rush-dev-secret")

    db.init_app(app)
    bcrypt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from api.auth import auth_bp
    from api.booking import booking_bp
    from api.customers import customers_bp
    from api.settings import settings_bp
    from api.tables import tables_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(tables_bp, url_prefix="/api/tables")
    app.register_blueprint(customers_bp, url_prefix="/api/customers")
    app.register_blueprint(settings_bp, url_prefix="/api/settings")
    app.register_blueprint(booking_bp, url_prefix="/api/booking")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"}), 200

    with app.app_context():
        db.create_all()
        seed_if_empty()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
