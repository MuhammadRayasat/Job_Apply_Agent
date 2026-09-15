"""
Entry point — run this to start the Job Apply Agent.
Usage: python run.py
"""
import os

# Must be set BEFORE any google/protobuf imports — fixes Python 3.14 compatibility
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from dotenv import load_dotenv
load_dotenv()

from modules.database import init_db
from app import app
from modules.scheduler import start_scheduler

if __name__ == "__main__":
    # Initialize DB (creates tables + runs migrations)
    init_db()

    # Start background scheduler (auto scrape + apply every 6 hours)
    scheduler = start_scheduler(app)

    print("\n" + "="*50)
    print("  Job Apply Agent is running!")
    print("  Open: http://localhost:5001")
    print("  Auto-cycle: every 15 minutes (background)")
    print("="*50 + "\n")

    try:
        app.run(debug=False, host="0.0.0.0", port=5001, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("\n[Server] Stopped.")
