# -*- coding: utf-8 -*-
# log/log.py

"""
Interface and convenience methods for general logging.
"""

import sys
import time
import string
import logging
from sink import StdOutSink, StdErrSink

FORMATTER = logging.Formatter(
                fmt='%(asctime)s %(levelname)-8s %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S')

def formatter():
    """Date and time format for logging, ISO 8601:2004"""
    return FORMATTER

def timestampFormat():
    """Format for current local time, suitable for file names.
    >>> timestampFormat()
    '%Y-%m-%d_%H-%M-%S'
    """
    return FORMATTER.datefmt.translate(string.maketrans(" :", "_-"))

def timestamp():
    """Current local time.
    >>> timestamp() == time.strftime("%Y-%m-%d_%H-%M-%S")
    True
    """
    return time.strftime(timestampFormat())

def replaceStdOutErr(sout = None, serr = None):
    """Replaces stdout/err with calls to logging.info/error."""
    if sout is None:
        sout = StdOutSink()
    if serr is None:
        serr = StdErrSink()
    sys.stdout = sout
    sys.stderr = serr
    # set custom log format for existing handlers
    handler = logging.StreamHandler(stream = sys.__stderr__)
    replaceHandler(handler)

def replaceHandler(handler):
    if handler is None:
        return
    # get a copy of existing handlers, remove them later
    rootLogger = logging.getLogger()
    oldHandlers = rootLogger.handlers[:]
    addHandler(handler)
    # remove previous existing handlers
    for h in oldHandlers:
        rootLogger.removeHandler(h)

def addHandler(handler):
    """Set up a new handler and add it for logging."""
    if handler is None:
        return
    rootLogger = logging.getLogger()
    handler.setFormatter(FORMATTER)
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.NOTSET)

def removeHandler(handler):
    try:
        handler.close()
    except:
        pass
    logging.getLogger().removeHandler(handler)

if __name__ == "__main__":
    # run embedded doc tests
    import doctest
    doctest.testmod()

# vim: set ts=4 sts=4 sw=4 tw=0: