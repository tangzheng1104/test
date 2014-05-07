# -*- coding: utf-8 -*-
# dockwidget.py

from cutesnake.qt import QtCore, QtGui
from QtCore import QDir, QSize, Qt
from QtGui import QApplication, QDockWidget, QWidget
from cutesnake.utils.signal import Signal
import inspect

class DockWidget(QDockWidget):
    """
    Widget for docking in a QMainWindow environment.

    """
    
    def __init__(self, parent, childWidgetType, *args, **kwargs):
        QDockWidget.__init__(self, parent)
        self.setFeatures(QDockWidget.DockWidgetFloatable|
                         QDockWidget.DockWidgetMovable)
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        childWidget = self._setupChildWidget(childWidgetType, *args, **kwargs)
        self.setWidget(childWidget)
        self.visibilityChanged.connect(self.onVisibilityChange)

    def _setupChildWidget(self, childWidgetType, *args, **kwargs):
        childWidget = childWidgetType(*args, parent = self, **kwargs)
        self.setObjectName(childWidget.objectName() + "Dock")
        self.setWindowTitle(childWidget.windowTitle())
        childWidget.title.registerUpdateFunc(self.setWindowTitle)
        return childWidget

    @property
    def child(self):
        assert isinstance(self.widget(), QWidget), \
                "No child widget added to this DockWidget"
        return self.widget()

    def onVisibilityChange(self, visible):
        if not visible or not self.isFloating():
            return
        # enlarge the floating window
        size = QSize()
        for widget in QApplication.topLevelWidgets():
            size = size.expandedTo(widget.size())
        self.resize(size)

    def closeEvent(self, event):
        event.ignore()
        self.setFloating(False)

# vim: set ts=4 sts=4 sw=4 tw=0:
