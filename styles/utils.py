
from PySide6.QtCore import QFile

def get_stylesheet(style_file):
    """
    Returns the stylesheet from a .qss file
    """
    style_file = QFile(style_file)
    style_file.open(QFile.ReadOnly | QFile.Text)
    stylesheet = style_file.readAll()
    stylesheet = str(stylesheet, encoding="utf-8")
    return stylesheet