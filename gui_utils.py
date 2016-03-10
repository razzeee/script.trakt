import xbmcgui
import time
import os
import xbmcaddon
from kodiUtilities import notification, setSetting, getString
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
    CENTER_Y = 6
    CENTER_X = 2

    logger = logging.getLogger(__name__)
    
    class PinAuthDialog(xbmcgui.WindowXMLDialog):
        auth = False
        
        def onInit(self):
            self.pin_edit_control = self.__add_editcontrol(30, 240, 40, 450)
            self.setFocus(self.pin_edit_control)
            auth = self.getControl(AUTH_BUTTON)
            never = self.getControl(NEVER_BUTTON)
            instuction = self.getControl(INSTRUCTION_LABEL)
            instuction.setLabel( "1) " + getString(32159).format("[COLOR red]http://trakt.tv/pin/999[/COLOR]") + "\n2) " + getString(32160) + "\n3) " + getString(32161) + "\n\n" + getString(32162))
            self.pin_edit_control.controlUp(never)
            self.pin_edit_control.controlLeft(never)
            self.pin_edit_control.controlDown(auth)
            self.pin_edit_control.controlRight(auth)
            auth.controlUp(self.pin_edit_control)
            auth.controlLeft(self.pin_edit_control)
            never.controlDown(self.pin_edit_control)
            never.controlRight(self.pin_edit_control)
            
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
            pin = self.pin_edit_control.getText().strip()
            if pin:
                try:
                    if traktapi.traktAPI().authenticate(pin):
                        return True
                except:
                    return False
            return False
        
        # have to add edit controls programatically because getControl() (hard) crashes XBMC on them
        def __add_editcontrol(self, x, y, height, width):
            media_path = os.path.join(__addon__.getAddonInfo('path'), 'resources', 'skins', 'Default', 'media')
            temp = xbmcgui.ControlEdit(0, 0, 0, 0, '', font='font12', textColor='0xFFFFFFFF', focusTexture=os.path.join(media_path, 'button-focus2.png'),
                                       noFocusTexture=os.path.join(media_path, 'button-nofocus.png'), _alignment=CENTER_Y | CENTER_X)
            temp.setPosition(x, y)
            temp.setHeight(height)
            temp.setWidth(width)
            self.addControl(temp)
            return temp
        
    dialog = PinAuthDialog('script-trakt-PinAuthDialog.xml', __addon__.getAddonInfo('path'))
    dialog.doModal()
    if dialog.auth:
        notification(getString(32157), getString(32152), 3000)
    del dialog
