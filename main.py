"""specdev — Hyperspectral Camera Ground Testing Application (地检软件)."""

from src.utils.logger import setup_logging
import argparse
import sys
import os
import logging

# Add daheng SDK to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "daheng-example"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="地检软件 — Hyperspectral Camera App")
    parser.add_argument("--mock", action="store_true",
                        help="Use simulated camera device")
    parser.add_argument("--debug", action="store_true",
                        help="Enable DEBUG console logging")
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    logger = logging.getLogger("specdev")
    logger.info("Starting specdev (mock=%s, debug=%s)", args.mock, args.debug)

    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon
    app = QApplication(sys.argv)
    app.setApplicationName("specdev")
    app.setOrganizationName("specdev")
    _ico = os.path.join(os.path.dirname(__file__), "assets", "app.ico")
    app.setWindowIcon(QIcon(_ico))

    # Create device
    if args.mock:
        from src.device.mock_device import MockDevice
        device = MockDevice()
    else:
        try:
            from src.device.daheng_device import DahengDevice
            device = DahengDevice()
        except ImportError as e:
            logger.warning(
                "Daheng SDK import failed (%s), falling back to MockDevice", e
            )
            from src.device.mock_device import MockDevice
            device = MockDevice()

    if not device.initialize():
        logger.error("Device initialization failed")
        error_detail = getattr(device, "last_error", "")
        message = "Failed to initialize the camera device."
        if error_detail:
            message = f"{message}\n\nReason: {error_detail}"
        QMessageBox.critical(
            None,
            "Device Initialization Failed",
            message,
        )
        sys.exit(1)

    # Create and show main window
    from src.ui.main_window import MainWindow
    window = MainWindow(device)
    window.show()

    logger.info("Application ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
