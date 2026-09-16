"""PyInstaller-safe launcher for the Windows GUI."""

from mcnp_report.gui import main


if __name__ == "__main__":
    raise SystemExit(main())
