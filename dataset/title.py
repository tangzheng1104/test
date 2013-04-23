# -*- coding: utf-8 -*-
# title.py

from utils import isString

class Title(object):
    _title = None

    def __init__(self, title):
        self.title = title

    @property
    def title(self):
        """
        Returns the title of this object for display in a GUI.
        """
        return self._title

    @title.setter
    def title(self, title):
        assert (title is not None and isString(title) and len(title) > 0), \
                "Expected a meaningful title!"
        self._title = title

# vim: set ts=4 sts=4 sw=4 tw=0:
