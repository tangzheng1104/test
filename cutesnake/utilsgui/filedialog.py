# -*- coding: utf-8 -*-
# filedialog.py

"""
File dialogs and convenience functions.

"""

import os
from cutesnake.qt import QtGui
from QtGui import QFileDialog, QDialog

def fileDialogType():
    if sys.platform.startswith('win'):
        return QDialog
    return QFileDialog

def makeFilter(filterList):
    if filterList is None:
        return ""
    return ";;".join(filterList)

def fileDialog(parent, labeltext, path, directory = False,
               readOnly = True):
    """
    Opens a dialog to select one or more files for reading.

    Alternative to native file dialogs.
    """
    if directory and not os.path.isdir(path):
        path = os.path.dirname(path)
    dialog = QFileDialog(parent, labeltext, path)
    options = dialog.options() | QFileDialog.ReadOnly
    mode = dialog.fileMode()
    if directory:
        mode = QFileDialog.Directory
        options |= QFileDialog.ShowDirsOnly
    if not readOnly:
        options &= ~QFileDialog.ReadOnly
    dialog.setFileMode(mode)
    dialog.setOptions(options)
    dialog.setViewMode(QFileDialog.Detail)
    return dialog

def getOpenFiles(parent, labeltext, path,
                 filefilter = None, multiple = True):
    kwargs = {'options': QFileDialog.ReadOnly,
              'caption': labeltext,
              'directory': path,
              'filter': makeFilter(filefilter)}
    if multiple:
        return list(QFileDialog.getOpenFileNames(parent, **kwargs))
    else:
        return [QFileDialog.getOpenFileName(parent, **kwargs)]

def getSaveFile(parent, labeltext, path, filefilter):
    fileList = QFileDialog.getSaveFileName(
        parent,
        caption = labeltext,
        directory = path,
        filter = makeFilter(filefilter))
    return fileList

def getSaveDirectory(parent, labeltext, path):
    if not os.path.isdir(path):
        path = os.path.dirname(path)
    dirList = QFileDialog.getExistingDirectory(
        parent,
        caption = labeltext,
        directory = path)
    return dirList

# vim: set ts=4 sts=4 sw=4 tw=0:
