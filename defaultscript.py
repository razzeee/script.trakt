# -*- coding: utf-8 -*-
import logging
import xbmcaddon
from resources.lib import script

logger = logging.getLogger(__name__)

__addon__ = xbmcaddon.Addon("script.trakt")

def Main():
    script.run()

if __name__ == '__main__':
    Main()
