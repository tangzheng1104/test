# -*- coding: utf-8 -*-
# qt.py

__all__ = ["QtGui", "QtCore", "QtSvg", "QtXml"]
#QTLIB = "PyQt4"
QTLIB = "PySide"
try:
    __import__(QTLIB)
except ImportError:
    #maybe we have PySide as fallback option
    QTLIB="PySide"
    print("Failed to import '{}'!".format(QTLIB))

import sys
import os
import importlib

thismodule = sys.modules[__name__]

# make qt modules available to be imported from this file/module
for libname in __all__:
    mod = importlib.import_module(".{0}".format(libname), QTLIB)
    sys.modules[libname] = mod
    setattr(thismodule, libname, mod)

def pluginDirs():
    libpath = sys.modules[QTLIB].__path__ # PySide.__path__
    for pdir in [os.path.join(p, "plugins") for p in libpath]:
        yield pdir

# vim: set ts=4 sts=4 sw=4 tw=0:
