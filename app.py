"""
Stock Analysis App — Flask entry point

Local:    python app.py  -> http://127.0.0.1:5000
Railway:  gunicorn ผ่าน Procfile (bind 0.0.0.0:$PORT)
"""
from flask import Flask, render_template

from config import Config
from database import init_db
from routes.api import api


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    init_db()
    app.register_blueprint(api)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    print(f"\n  Stock Analysis App running at http://{Config.HOST}:{Config.PORT}\n")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
