import xbmcgui
import time
import os
import xbmcaddon
from utilities import notification, setSetting, getString
import traktapi
import logging

__addon__ = xbmcaddon.Addon("script.trakt")

def get_pin():
    AUTH_BUTTON = 200
    LATER_BUTTON = 201
    NEVER_BUTTON = 202
    ACTION_PREVIOUS_MENU = 10
    ACTION_BACK = 92
    INSTRUCTION_LABEL = 203

    PIN_EDIT = 3001

    logger = logging.getLogger(__name__)
    
    class PinAuthDialog(xbmcgui.WindowXMLDialog):
        auth = False
        
        def onInit(self):
            self.pin = self.getControl(PIN_EDIT)
            self.setFocus(self.pin)
            auth = self.getControl(AUTH_BUTTON)
            never = self.getControl(NEVER_BUTTON)
            instuction = self.getControl(INSTRUCTION_LABEL)

            if xbmcgui.Window(10000).getProperty('script.trakt.linkcolor'):
                linkcolor = xbmcgui.Window(10000).getProperty('script.trakt.linkcolor')
            else:
                linkcolor = 'red'

            instuction.setLabel("1) " + getString(32159).format("[COLOR "+ linkcolor +"]http://trakt.tv/pin/999[/COLOR]") + "\n2) " + getString(32160) + "\n3) " + getString(32161) + "\n\n" + getString(32162))
            self.pin.controlUp(never)
            self.pin.controlLeft(never)
            self.pin.controlDown(auth)
            self.pin.controlRight(auth)
            auth.controlUp(self.pin)
            auth.controlLeft(self.pin)
            never.controlDown(self.pin)
            never.controlRight(self.pin)
            
        def onAction(self, action):
            #print 'Action: %s' % (action.getId())
            if action == ACTION_PREVIOUS_MENU or action == ACTION_BACK:
                self.close()

        def onControl(self, control):
            #print 'onControl: %s' % (control)
            pass

        def onFocus(self, control):
            #print 'onFocus: %s' % (control)
            pass

        def onClick(self, control):
            #print 'onClick: %s' % (control)
            logger.debug('onClick: %s' % (control))
            if control == AUTH_BUTTON:
                if not self.__get_token():
                    logger.debug("Authentification error")
                    notification(getString(32157), getString(32147), 5000)
                    return
                self.auth = True

            if control == LATER_BUTTON:
                notification(getString(32157), getString(32150), 5000)
                setSetting('last_reminder', str(int(time.time())))

            if control == NEVER_BUTTON:
                notification(getString(32157), getString(32151), 5000)
                setSetting('last_reminder', '-1')

            if control in [AUTH_BUTTON, LATER_BUTTON, NEVER_BUTTON]:
                self.close()
        
        def __get_token(self):
            pin = self.pin.getText().strip()
            if pin:
                try:
                    if traktapi.traktAPI().authenticate(pin):
                        return True
                except:
                    return False
            return False

    dialog = PinAuthDialog('script-trakt-PinAuthDialog.xml', __addon__.getAddonInfo('path'))
    dialog.doModal()
    if dialog.auth:
        notification(getString(32157), getString(32152), 3000)
    del dialog
