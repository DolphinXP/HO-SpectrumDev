"""gpy4 — Hyperspectral Camera Ground Testing Application (地检软件)."""

import argparse
import sys
import os
import logging

# Add daheng SDK to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "daheng-example"))

from src.utils.logger import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="地检软件 — Hyperspectral Camera App")
    parser.add_argument("--mock", action="store_true", help="Use simulated camera device")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG console logging")
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    logger = logging.getLogger("gpy4")
    logger.info("Starting gpy4 (mock=%s, debug=%s)", args.mock, args.debug)

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("gpy4")
    app.setOrganizationName("gpy4")

    # Create device
    if args.mock:
        from src.device.mock_device import MockDevice
        device = MockDevice()
    else:
        try:
            from src.device.daheng_device import DahengDevice
            device = DahengDevice()
        except ImportError:
            logger.warning("Daheng SDK not available, falling back to MockDevice")
            from src.device.mock_device import MockDevice
            device = MockDevice()

    if not device.initialize():
        logger.error("Device initialization failed")
        sys.exit(1)

    # Create and show main window
    from src.ui.main_window import MainWindow
    window = MainWindow(device)
    window.show()

    logger.info("Application ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
