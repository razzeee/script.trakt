"""Module used to launch rating dialogues and send ratings to Trakt"""

import logging
from typing import Any, ClassVar

import xbmcaddon
import xbmcgui

from resources.lib import globals, kodiUtilities, utilities

logger = logging.getLogger(__name__)

__addon__ = xbmcaddon.Addon("script.trakt")


def ratingCheck(
    media_type: str, items_to_rate: list[dict], watched_time: float, total_time: float
) -> None:
    """Check if a video should be rated and if so launches the rating dialog"""
    logger.debug(f"Rating Check called for '{media_type}'")
    if not kodiUtilities.getSettingAsBool(f"rate_{media_type}"):
        logger.debug(f"'{media_type}' is configured to not be rated.")
        return
    if items_to_rate is None:
        logger.debug("Summary information is empty, aborting.")
        return
    watched = (watched_time / total_time) * 100
    if watched >= kodiUtilities.getSettingAsFloat("rate_min_view_time"):
        rateMedia(media_type, items_to_rate)
    else:
        logger.debug(
            "'{}' does not meet minimum view time for rating (watched: {:0.2f}%, minimum: {:0.2f}%)".format(
                media_type,
                watched,
                kodiUtilities.getSettingAsFloat("rate_min_view_time"),
            )
        )


def rateMedia(
    media_type: str,
    itemsToRate: list[dict],
    unrate: bool = False,
    rating: int | str | None = None,
) -> None:
    """Launches the rating dialog"""
    for summary_info in itemsToRate:
        if not utilities.isValidMediaType(media_type):
            logger.debug("Not a valid media type")
            return
        elif "user" not in summary_info:
            logger.debug("No user data")
            return

        s = utilities.getFormattedItemName(media_type, summary_info)

        logger.debug(f"Summary Info {summary_info}")

        if unrate:
            rating = None

            if summary_info["user"]["ratings"]["rating"] > 0:
                rating = 0

            if rating is not None:
                logger.debug(f"'{s}' is being unrated.")
                __rateOnTrakt(rating, media_type, summary_info, unrate=True)
            else:
                logger.debug(f"'{s}' has not been rated, so not unrating.")

            return

        rerate = kodiUtilities.getSettingAsBool("rate_rerate")
        if rating is not None:
            if summary_info["user"]["ratings"]["rating"] == 0:
                logger.debug(
                    f"Rating for '{s:s}' is being set to '{rating:d}' manually."
                )
                __rateOnTrakt(rating, media_type, summary_info)
            else:
                if rerate:
                    if summary_info["user"]["ratings"]["rating"] != rating:
                        logger.debug(
                            f"Rating for '{s:s}' is being set to '{rating:d}' manually."
                        )
                        __rateOnTrakt(rating, media_type, summary_info)
                    else:
                        kodiUtilities.notification(kodiUtilities.getString(32043), s)
                        logger.debug(f"'{s:s}' already has a rating of '{rating:d}'.")
                else:
                    kodiUtilities.notification(kodiUtilities.getString(32041), s)
                    logger.debug(f"'{s}' is already rated.")
            return

        if (
            summary_info["user"]["ratings"]
            and summary_info["user"]["ratings"]["rating"]
        ):
            if not rerate:
                logger.debug(f"'{s}' has already been rated.")
                kodiUtilities.notification(kodiUtilities.getString(32041), s)
                return
            else:
                logger.debug(f"'{s}' is being re-rated.")

        gui = RatingDialog(
            "script-trakt-RatingDialog.xml",
            __addon__.getAddonInfo("path"),
            media_type,
            summary_info,
            rerate,
        )

        gui.doModal()
        if gui.rating:
            rating = gui.rating
            if rerate and (
                summary_info["user"]["ratings"]
                and summary_info["user"]["ratings"]["rating"] > 0
                and rating == summary_info["user"]["ratings"]["rating"]
            ):
                rating = 0

            if rating == 0 or rating == "unrate":
                __rateOnTrakt(rating, gui.media_type, gui.media, unrate=True)
            else:
                __rateOnTrakt(rating, gui.media_type, gui.media)
        else:
            logger.debug("Rating dialog was closed with no rating.")

        del gui
        # Reset rating and unrate for multi part episodes
        unrate = False
        rating = None


def __rateOnTrakt(
    rating: int | str, media_type: str, media: dict, unrate: bool = False
) -> None:
    logger.debug(f"Sending rating ({rating}) to Trakt.tv")

    params = media
    if utilities.isMovie(media_type):
        key = "movies"
        params["rating"] = rating
        if "movieid" in media:
            kodiUtilities.kodiJsonRequest(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "VideoLibrary.SetMovieDetails",
                    "params": {"movieid": media["movieid"], "userrating": rating},
                }
            )
    elif utilities.isShow(media_type):
        key = "shows"
        # we need to remove this key or trakt will be confused
        del params["seasons"]
        params["rating"] = rating
        if "tvshowid" in media:
            kodiUtilities.kodiJsonRequest(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "VideoLibrary.SetTVShowDetails",
                    "params": {"tvshowid": media["tvshowid"], "userrating": rating},
                }
            )
    elif utilities.isSeason(media_type):
        key = "shows"
        params["seasons"] = [{"rating": rating, "number": media["season"]}]
    elif utilities.isEpisode(media_type):
        key = "episodes"
        params["rating"] = rating
        if "episodeid" in media:
            kodiUtilities.kodiJsonRequest(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "VideoLibrary.SetEpisodeDetails",
                    "params": {"episodeid": media["episodeid"], "userrating": rating},
                }
            )
    else:
        return
    root = {key: [params]}

    if not unrate:
        data = globals.traktapi.addRating(root)
    else:
        data = globals.traktapi.removeRating(root)

    if data:
        s = utilities.getFormattedItemName(media_type, media)
        if (
            "not_found" in data
            and not data["not_found"]["movies"]
            and not data["not_found"]["episodes"]
            and not data["not_found"]["shows"]
        ):
            if not unrate:
                kodiUtilities.notification(kodiUtilities.getString(32040), s)
            else:
                kodiUtilities.notification(kodiUtilities.getString(32042), s)
        else:
            kodiUtilities.notification(kodiUtilities.getString(32044), s)


class RatingDialog(xbmcgui.WindowXMLDialog):
    media_type: str
    media: dict
    rating: int | str | None
    rerate: bool
    default_rating: int

    buttons: ClassVar[dict[int, int]] = {
        11030: 1,
        11031: 2,
        11032: 3,
        11033: 4,
        11034: 5,
        11035: 6,
        11036: 7,
        11037: 8,
        11038: 9,
        11039: 10,
    }

    focus_labels: ClassVar[dict[int, int]] = {
        11030: 32028,
        11031: 32029,
        11032: 32030,
        11033: 32031,
        11034: 32032,
        11035: 32033,
        11036: 32034,
        11037: 32035,
        11038: 32036,
        11039: 32027,
    }

    def __init__(
        self,
        xmlFile: str,
        resourcePath: str,
        media_type: str,
        media: dict,
        rerate: bool,
    ) -> None:
        self.media_type = media_type
        self.media = media
        self.rating = None
        self.rerate = rerate
        self.default_rating = kodiUtilities.getSettingAsInt("rating_default")

    def __new__(
        cls, xmlFile: str, resourcePath: str, media_type: str, media: dict, rerate: bool
    ) -> Any:
        return super().__new__(cls, xmlFile, resourcePath)

    def onInit(self) -> None:
        s = utilities.getFormattedItemName(self.media_type, self.media)
        self.getControl(10012).setLabel(s)

        rateID = 11029 + self.default_rating
        if (
            self.rerate
            and self.media["user"]["ratings"]
            and int(self.media["user"]["ratings"]["rating"]) > 0
        ):
            rateID = 11029 + int(self.media["user"]["ratings"]["rating"])
        self.setFocus(self.getControl(rateID))

    def onClick(self, controlID: int) -> None:
        if controlID in self.buttons:
            self.rating = self.buttons[controlID]
            self.close()

    def onFocus(self, controlID: int) -> None:
        if controlID in self.focus_labels:
            s = kodiUtilities.getString(self.focus_labels[controlID])

            if self.rerate and (
                self.media["user"]["ratings"]
                and self.media["user"]["ratings"]["rating"] == self.buttons[controlID]
            ):
                if utilities.isMovie(self.media_type):
                    s = kodiUtilities.getString(32037)
                elif utilities.isShow(self.media_type):
                    s = kodiUtilities.getString(32038)
                elif utilities.isEpisode(self.media_type):
                    s = kodiUtilities.getString(32039)
                elif utilities.isSeason(self.media_type):
                    s = kodiUtilities.getString(32132)
                else:
                    pass

            self.getControl(10013).setLabel(s)
        else:
            self.getControl(10013).setLabel("")
