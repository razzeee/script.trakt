import logging

import xbmcaddon

from resources.lib import kodilogging
from resources.lib.kodiUtilities import getSetting, setSetting
from resources.lib.service import traktService
from resources.lib.utilities import checkIfNewVersion, createError

__addon__ = xbmcaddon.Addon("script.trakt")
__addonversion__ = __addon__.getAddonInfo("version")
__addonid__ = __addon__.getAddonInfo("id")
kodilogging.config()
logger = logging.getLogger(__name__)

logger.debug(f"Loading '{__addonid__}' version '{__addonversion__}'")
if checkIfNewVersion(str(getSetting("version")), str(__addonversion__)):
    setSetting("version", __addonversion__)

try:
    traktService().run()
except Exception as ex:  # noqa: BLE001 - preserve the existing broad failure boundary
    message = createError(ex)
    logger.fatal(message)

logger.debug(f"'{__addonid__}' shutting down.")
