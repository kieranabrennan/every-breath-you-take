
from PySide6.QtCharts import QChart, QLineSeries, QValueAxis, QScatterSeries, QSplineSeries
from PySide6.QtGui import QPen, QFont
from styles.colours import GRAY

def create_chart(title=None, showTitle=False, showLegend=False, margins=None):
        chart = QChart()
        chart.legend().setVisible(showLegend)
        chart.setTitle(title)
        if margins:
            chart.setMargins(margins)
            chart.layout().setContentsMargins(margins)
        return chart
    
def create_scatter_series(color=None, size=5):
    if color is None:
        color = GRAY
    series = QScatterSeries()
    series.setMarkerSize(size)
    series.setMarkerShape(QScatterSeries.MarkerShapeCircle)
    series.setColor(color)
    series.setBorderColor(color)
    return series

def create_line_series(color=None, width=2, style=None):
    if color is None:
        color = GRAY
    series = QLineSeries()
    pen = QPen(color)
    pen.setWidth(width)
    if style:
        pen.setStyle(style)
    series.setPen(pen)
    return series

def create_spline_series(color=None, width=2):
    if color is None:
        color = GRAY
    series = QSplineSeries()
    pen = QPen(color)
    pen.setWidth(width)
    series.setPen(pen)
    return series

def create_axis(title=None, color=None, tickCount=None, rangeMin=None, rangeMax=None, labelSize=None, flip=False):
    if color is None:
        color = GRAY
    axis = QValueAxis()
    axis.setTitleText(title)
    axis.setLabelsColor(color)
    axis.setTitleBrush(color)
    axis.setGridLineVisible(False)
    if tickCount:
        axis.setTickCount(tickCount)
    if rangeMin:
        axis.setMin(rangeMin)
    if rangeMax:
        axis.setMax(rangeMax)
    if labelSize:
        font = QFont()
        font.setPointSize(labelSize)
        axis.setLabelsFont(font)
    if flip:
        axis.setReverse(True)
    return axis