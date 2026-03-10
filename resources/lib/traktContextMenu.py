# -*- coding: utf-8 -*-

import xbmcaddon
import xbmcgui
from typing import List, Optional, Any
from resources.lib.utilities import isMovie, isShow, isSeason, isEpisode
from resources.lib.kodiUtilities import getString

__addon__ = xbmcaddon.Addon("script.trakt")

ACTION_LIST = 111
DIALOG_IMAGE = 2
ACTION_PREVIOUS_MENU2 = 92
ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_SELECT_ITEM = 7
ACTION_MOUSE_LEFT_CLICK = 100
ACTION_CLOSE_LIST = [ACTION_PREVIOUS_MENU2, ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU]
ACTION_ITEM_SELECT = [ACTION_SELECT_ITEM, ACTION_MOUSE_LEFT_CLICK]


class traktContextMenu(xbmcgui.WindowXMLDialog):
    action: Optional[str] = None
    buttons: List[str]
    media_type: str

    def __new__(
        cls, media_type: Optional[str] = None, buttons: Optional[List[str]] = None
    ) -> Any:
        return super(traktContextMenu, cls).__new__(
            cls,
            "script-trakt-ContextMenu.xml",
            __addon__.getAddonInfo("path"),
            media_type=media_type,
            buttons=None,
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.buttons = kwargs["buttons"]
        self.media_type = kwargs["media_type"]
        super(traktContextMenu, self).__init__()

    def onInit(self) -> None:
        mange_string = (
            getString(32133) if isMovie(self.media_type) else getString(32134)
        )
        rate_string = getString(32137)
        if isShow(self.media_type):
            rate_string = getString(32138)
        elif isSeason(self.media_type):
            rate_string = getString(32149)
        elif isEpisode(self.media_type):
            rate_string = getString(32139)

        actions = [
            mange_string,
            getString(32135),
            getString(32136),
            rate_string,
            getString(32140),
            getString(32141),
            getString(32142),
            getString(32143),
        ]
        keys = [
            "itemlists",
            "removefromlist",
            "addtowatchlist",
            "rate",
            "togglewatched",
            "managelists",
            "updatetags",
            "sync",
        ]

        actionList = self.getControl(ACTION_LIST)
        for i in range(len(actions)):
            if keys[i] in self.buttons:
                actionList.addItem(self.newListItem(actions[i], id=keys[i]))

        self.setFocus(actionList)

    def newListItem(
        self, label: str, selected: bool = False, *args: Any, **kwargs: Any
    ) -> xbmcgui.ListItem:
        item = xbmcgui.ListItem(label)
        item.select(selected)
        for key in kwargs:
            item.setProperty(key, str(kwargs[key]))
        return item

    def onAction(self, action: xbmcgui.Action) -> None:
        if action.getId() not in ACTION_ITEM_SELECT:
            if action in ACTION_CLOSE_LIST:
                self.close()

        if action in ACTION_ITEM_SELECT:
            cID = self.getFocusId()
            if cID == ACTION_LIST:
                control = self.getControl(cID)
                item = control.getSelectedItem()
                self.action = item.getProperty("id")
                self.close()
