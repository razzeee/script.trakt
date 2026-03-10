# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Thomas Amland
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from resources.lib.kodiUtilities import getSettingAsBool

import logging
import xbmc
import xbmcaddon


class KodiLogHandler(logging.StreamHandler):

    def __init__(self) -> None:
        logging.StreamHandler.__init__(self)
        addon_id = xbmcaddon.Addon().getAddonInfo('id')
        prefix = "[%s] " % addon_id
        formatter = logging.Formatter(prefix + '%(name)s: %(message)s')
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        levels = {
            logging.CRITICAL: xbmc.LOGFATAL,
            logging.ERROR: xbmc.LOGERROR,
            logging.WARNING: xbmc.LOGWARNING,
            logging.INFO: xbmc.LOGINFO,
            logging.DEBUG: xbmc.LOGDEBUG,
            logging.NOTSET: xbmc.LOGNONE,
        }
        if getSettingAsBool('debug'):
            xbmc.log(self.format(record), levels[record.levelno])

    def flush(self) -> None:
        pass

def config() -> None:
    logger = logging.getLogger()
    logger.addHandler(KodiLogHandler())
    logger.setLevel(logging.DEBUG)
