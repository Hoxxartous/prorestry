import os
from dotenv import load_dotenv
from app import create_app, socketio
from edge_config import EdgeConfig


def main():
    """Start the Branch Edge server using local SQLite.

    This runs the same Flask application in Edge mode so cashiers and kitchens
    can continue working over Wi‑Fi without internet.
    """
    # Load environment from .env if present (CLOUD_SYNC_BASE_URL, SYNC_API_TOKEN, etc.)
    try:
        load_dotenv()
    except Exception:
        pass

    app = create_app(EdgeConfig)

    # Optional: allow overriding host/port via environment
    host = os.getenv('EDGE_HOST', '0.0.0.0')
    port = int(os.getenv('EDGE_PORT', '8443'))
    debug = os.getenv('EDGE_DEBUG', '0') in ['1', 'true', 'True']

    # Print helpful startup message
    print("\n================ EDGE MODE ================")
    print(f"SQLite DB: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    print(f"Listening on: http://{host}:{port}")
    print("Connect POS and Kitchen devices to the same Wi‑Fi and open the URL above.")
    print("==========================================\n")

    # Run Socket.IO server for real-time cashier ↔ kitchen updates
    socketio.run(app, host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
