# PyInstaller one-folder build for Windows.
# Run from this folder: pyinstaller --noconfirm rollover_windows.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()

all_datas = [
    (str(ROOT / "rolldown_dashboard_app.py"), "."),
    (str(ROOT / "rolldown_engine_prototype_v4.py"), "."),
    (str(ROOT / "data" / "Gsec daily price data.xlsx"), "data"),
    (str(ROOT / "data" / "Daily_Repo.xlsx"), "data"),
    (str(ROOT / ".streamlit" / "config.toml"), ".streamlit"),
]
all_binaries = []
all_hiddenimports = [
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "openpyxl.cell._writer",
    "plotly.express",
]

for package in ("streamlit", "pandas", "numpy", "plotly", "openpyxl", "altair", "pyarrow"):
    datas, binaries, hiddenimports = collect_all(package)

    # Exclude Streamlit development-only assets
    # that are not required to run the dashboard.
    datas = [
        (src, dest)
        for src, dest in datas
        if "/.agents/" not in src.replace("\\", "/").lower()
    ]

    # Exclude pandas test modules from the packaged application.
    hiddenimports = [
        name for name in hiddenimports
        if not name.startswith("pandas.tests")
    ]

    all_datas += datas
    all_binaries += binaries
    all_hiddenimports += hiddenimports


a = Analysis(
    [str(ROOT / "rollover_launcher.py")],
    pathex=[str(ROOT)],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ROLLOVER",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ROLLOVER",
)
