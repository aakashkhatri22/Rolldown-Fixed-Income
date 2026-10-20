
import os
import sys
import time
import threading
import webbrowser
from pathlib import Path


def main():
    # Locate the bundled application files
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        internal_dir = exe_dir / "_internal"

        if (internal_dir / "rolldown_dashboard_app.py").exists():
            app_dir = internal_dir
        else:
            app_dir = exe_dir
    else:
        app_dir = Path(__file__).resolve().parent

    dashboard = app_dir / "rolldown_dashboard_app.py"

    if not dashboard.exists():
        raise FileNotFoundError(
            f"Dashboard script not found. Checked: {dashboard}"
        )

    os.chdir(app_dir)

    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    # Open the dashboard automatically
    def open_browser():
        time.sleep(3)
        webbrowser.open("http://localhost:8501")

    threading.Thread(target=open_browser, daemon=True).start()

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(dashboard),
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.port=8501",
        "--browser.gatherUsageStats=false",
    ]

    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
