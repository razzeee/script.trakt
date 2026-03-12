import xbmcgui
import time
import xbmcaddon
from resources.lib.kodiUtilities import notification, setSetting, getString
import logging

__addon__ = xbmcaddon.Addon("script.trakt")

LATER_BUTTON = 201
NEVER_BUTTON = 202
ACTION_PREVIOUS_MENU = 10
ACTION_BACK = 92
INSTRUCTION_LABEL = 203
AUTHCODE_LABEL = 204
WARNING_LABEL = 205
CENTER_Y = 6
CENTER_X = 2

logger = logging.getLogger(__name__)


class DeviceAuthDialog(xbmcgui.WindowXMLDialog):
    code: str
    url: str

    def __init__(self, xmlFile: str, resourcePath: str, code: str, url: str) -> None:
        self.code = code
        self.url = url

    def onInit(self) -> None:
        instuction = self.getControl(INSTRUCTION_LABEL)
        authcode = self.getControl(AUTHCODE_LABEL)
        warning = self.getControl(WARNING_LABEL)
        instuction.setLabel(
            getString(32159).format("[COLOR red]" + self.url + "[/COLOR]")
        )
        authcode.setLabel(self.code)
        warning.setLabel(getString(32162))

    def onAction(self, action: xbmcgui.Action) -> None:
        if action == ACTION_PREVIOUS_MENU or action == ACTION_BACK:
            self.close()

    def onControl(self, control: xbmcgui.Control) -> None:
        pass

    def onFocus(self, control: xbmcgui.Control) -> None:
        pass

    def onClick(self, control: xbmcgui.Control) -> None:
        logger.debug("onClick: %s" % (control))

        if control == LATER_BUTTON:
            notification(getString(32157), getString(32150), 5000)
            setSetting("last_reminder", str(int(time.time())))

        if control == NEVER_BUTTON:
            notification(getString(32157), getString(32151), 5000)
            setSetting("last_reminder", "-1")

        if control in [LATER_BUTTON, NEVER_BUTTON]:
            self.close()
