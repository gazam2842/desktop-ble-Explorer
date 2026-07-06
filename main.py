"""BLE Explorer entry point. Runs the asyncio loop on top of Qt using qasync."""

import asyncio
import sys

import qasync
from PyQt6.QtWidgets import QApplication

from ble.uuid_names import AliasStore
from controller import Controller
from ui.main_window import MainWindow
from ui.theme import apply_theme, saved_theme


def main() -> None:
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    apply_theme(app, saved_theme())

    alias_store = AliasStore()
    alias_warning = alias_store.load()

    controller = Controller()
    window = MainWindow(controller, alias_store)
    window.show()
    if alias_warning:
        window.statusBar().showMessage(alias_warning)

    with loop:
        loop.run_forever()
        # Clean up all sessions/scan after the window closes
        loop.run_until_complete(controller.shutdown())


if __name__ == "__main__":
    main()
