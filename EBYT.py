
import os
os.environ['QT_API'] = 'PySide6' # For qasync to know which binding is being used
os.environ['QT_LOGGING_RULES'] = 'qt.pointer.dispatch=false' # Disable pointer logging

import sys
import asyncio
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
from View import View
import logging

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    plot = View()
    plot.setWindowTitle("Rolling Plot")
    plot.resize(1200, 600)
    plot.show()

    loop.create_task(plot.main())
    loop.run_forever()
