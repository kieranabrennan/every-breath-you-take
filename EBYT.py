
import os
os.environ['QT_API'] = 'PySide6' # For asyncqt to know which binding is being used
os.environ['QT_LOGGING_RULES'] = 'qt.pointer.dispatch=false' # Disable pointer logging

import sys
import asyncio
from PySide6.QtWidgets import QApplication
from asyncqt import QEventLoop
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
