import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from View import View

if __name__ == "__main__":

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    plot = View()
    plot.setWindowTitle("Rolling Plot")
    plot.resize(1200, 600)
    plot.show()

    loop.run_until_complete(plot.main())
