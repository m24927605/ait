# build/ait.spec — PyInstaller spec for `ait` standalone binary.
# Run from repo root: pyinstaller --clean --noconfirm build/ait.spec
# Output: build/dist/ait

a = Analysis(
    ["../src/ait/__main__.py"],
    pathex=["../src"],
    binaries=[],
    datas=[("../src/ait/resources", "ait/resources")],
    hiddenimports=[
        "ait.bug_report",
        "ait.bug_report.api",
        "ait.bug_report.collector",
        "ait.bug_report.excepthook",
        "ait.bug_report.flush",
        "ait.bug_report.prompt",
        "ait.bug_report.builder",
        "ait.bug_report.submitter",
        "ait.bug_report.pending_queue",
        "ait.bug_report.seen_store",
        "ait.bug_report.config",
        "ait.bug_report.fingerprint",
        "ait.bug_report.redactor",
        "ait.bug_report.safety",
        "ait._frozen_version",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["test", "tests", "unittest", "doctest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="ait",
    onefile=True,
    console=True,
    strip=True,
    upx=False,
    target_arch=None,
)
