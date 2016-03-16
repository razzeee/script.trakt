import xbmcgui
import time
import os
import xbmcaddon
from kodiUtilities import notification, setSetting, getString
import traktapi
import logging

__addon__ = xbmcaddon.Addon("script.trakt")

def get_auth(code, url):
    LATER_BUTTON = 201
    NEVER_BUTTON = 202
    ACTION_PREVIOUS_MENU = 10
    ACTION_BACK = 92
    INSTRUCTION_LABEL = 203
    CENTER_Y = 6
    CENTER_X = 2

    logger = logging.getLogger(__name__)
    
    class DeviceAuthDialog(xbmcgui.WindowXMLDialog):
        auth = False
        
        def onInit(self):
            never = self.getControl(NEVER_BUTTON)
            instuction = self.getControl(INSTRUCTION_LABEL)
            instuction.setLabel( getString(32159).format("[COLOR red]"+ url +"[/COLOR]") + "\n\n" + code + "\n\n" + getString(32162))
            
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

            if control == LATER_BUTTON:
                notification(getString(32157), getString(32150), 5000)
                setSetting('last_reminder', str(int(time.time())))

            if control == NEVER_BUTTON:
                notification(getString(32157), getString(32151), 5000)
                setSetting('last_reminder', '-1')

            if control in [LATER_BUTTON, NEVER_BUTTON]:
                self.close()
        
    dialog = DeviceAuthDialog('script-trakt-DeviceAuthDialog.xml', __addon__.getAddonInfo('path'))
    dialog.doModal()
    if dialog.auth:
        notification(getString(32157), getString(32152), 3000)
    del dialog
