# -*- coding: utf-8 -*-
"""Module used to launch rating dialogues and send ratings to Trakt"""

import xbmc
import xbmcaddon
import xbmcgui
import utilities
import kodiUtilities
import globals
import logging

logger = logging.getLogger(__name__)

__addon__ = xbmcaddon.Addon("script.trakt")

def ratingCheck(media_type, summary_info, watched_time, total_time, playlist_length):
    """Check if a video should be rated and if so launches the rating dialog"""
    logger.debug("Rating Check called for '%s'" % media_type)
    if not kodiUtilities.getSettingAsBool("rate_%s" % media_type):
        logger.debug("'%s' is configured to not be rated." % media_type)
        return
    if summary_info is None:
        logger.debug("Summary information is empty, aborting.")
        return
    watched = (watched_time / total_time) * 100
    if watched >= kodiUtilities.getSettingAsFloat("rate_min_view_time"):
        if (playlist_length <= 1) or kodiUtilities.getSettingAsBool("rate_each_playlist_item"):
            rateMedia(media_type, summary_info)
        else:
            logger.debug("Rate each playlist item is disabled.")
    else:
        logger.debug("'%s' does not meet minimum view time for rating (watched: %0.2f%%, minimum: %0.2f%%)" % (media_type, watched, kodiUtilities.getSettingAsFloat("rate_min_view_time")))

def rateMedia(media_type, itemsToRate, unrate=False, rating=None):
    """Launches the rating dialog"""
    for summary_info in itemsToRate:
        if not utilities.isValidMediaType(media_type):
            logger.debug("Not a valid media type")
            return
        elif 'user' not in summary_info:
            logger.debug("No user data")
            return

        s = utilities.getFormattedItemName(media_type, summary_info)

        logger.debug("Summary Info %s" % summary_info)

        if unrate:
            rating = None

            if summary_info['user']['ratings']['rating'] > 0:
                rating = 0

            if not rating is None:
                logger.debug("'%s' is being unrated." % s)
                __rateOnTrakt(rating, media_type, summary_info, unrate=True)
            else:
                logger.debug("'%s' has not been rated, so not unrating." % s)

            return

        rerate = kodiUtilities.getSettingAsBool('rate_rerate')
        if rating is not None:
            if summary_info['user']['ratings']['rating'] == 0:
                logger.debug("Rating for '%s' is being set to '%d' manually." % (s, rating))
                __rateOnTrakt(rating, media_type, summary_info)
            else:
                if rerate:
                    if not summary_info['user']['ratings']['rating'] == rating:
                        logger.debug("Rating for '%s' is being set to '%d' manually." % (s, rating))
                        __rateOnTrakt(rating, media_type, summary_info)
                    else:
                        kodiUtilities.notification(kodiUtilities.getString(32043), s)
                        logger.debug("'%s' already has a rating of '%d'." % (s, rating))
                else:
                    kodiUtilities.notification(kodiUtilities.getString(32041), s)
                    logger.debug("'%s' is already rated." % s)
            return

        if summary_info['user']['ratings'] and summary_info['user']['ratings']['rating']:
            if not rerate:
                logger.debug("'%s' has already been rated." % s)
                kodiUtilities.notification(kodiUtilities.getString(32041), s)
                return
            else:
                logger.debug("'%s' is being re-rated." % s)

        xbmc.executebuiltin('Dialog.Close(all, true)')

        gui = RatingDialog(
            "script-trakt-RatingDialog.xml",
            __addon__.getAddonInfo('path'),
            media_type=media_type,
            media=summary_info,
            rerate=rerate
        )

        gui.doModal()
        if gui.rating:
            rating = gui.rating
            if rerate:
                rating = gui.rating

                if summary_info['user']['ratings'] and summary_info['user']['ratings']['rating'] > 0 and rating == summary_info['user']['ratings']['rating']:
                    rating = 0

            if rating == 0 or rating == "unrate":
                __rateOnTrakt(rating, gui.media_type, gui.media, unrate=True)
            else:
                __rateOnTrakt(rating, gui.media_type, gui.media)
        else:
            logger.debug("Rating dialog was closed with no rating.")

        del gui
        #Reset rating and unrate for multi part episodes
        unrate=False
        rating=None

def __rateOnTrakt(rating, media_type, media, unrate=False):
    logger.debug("Sending rating (%s) to Trakt.tv" % rating)

    params = media
    if utilities.isMovie(media_type):
        key = 'movies'
        params['rating'] = rating
        if 'movieid' in media:
            kodiUtilities.kodiJsonRequest({"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": media['movieid'], "userrating": rating}})
    elif utilities.isShow(media_type):
        key = 'shows'
        params['rating'] = rating
        if 'tvshowid' in media:
            kodiUtilities.kodiJsonRequest({"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.SetTVShowDetails", "params": {"tvshowid": media['tvshowid'], "userrating": rating}})
    elif utilities.isSeason(media_type):
        key = 'shows'
        params['seasons'] = [{'rating': rating, 'number': media['season']}]
    elif utilities.isEpisode(media_type):
        key = 'episodes'
        params['rating'] = rating
        if 'episodeid' in media:
            kodiUtilities.kodiJsonRequest({"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid": media['episodeid'], "userrating": rating}})
    else:
        return
    root = {key: [params]}

    if not unrate:
        data = globals.traktapi.addRating(root)
    else:
        data = globals.traktapi.removeRating(root)

    if data:
        s = utilities.getFormattedItemName(media_type, media)
        if 'not_found' in data and not data['not_found']['movies'] and not data['not_found']['episodes'] and not data['not_found']['shows']:

            if not unrate:
                kodiUtilities.notification(kodiUtilities.getString(32040), s)
            else:
                kodiUtilities.notification(kodiUtilities.getString(32042), s)
        else:
            kodiUtilities.notification(kodiUtilities.getString(32044), s)

class RatingDialog(xbmcgui.WindowXMLDialog):
    buttons = {
        11030: 1,
        11031: 2,
        11032: 3,
        11033: 4,
        11034: 5,
        11035: 6,
        11036: 7,
        11037: 8,
        11038: 9,
        11039: 10
    }

    focus_labels = {
        11030: 32028,
        11031: 32029,
        11032: 32030,
        11033: 32031,
        11034: 32032,
        11035: 32033,
        11036: 32034,
        11037: 32035,
        11038: 32036,
        11039: 32027
    }

    def __init__(self, xmlFile, resourcePath, forceFallback=False, media_type=None, media=None, rerate=False):
        self.media_type = media_type
        self.media = media
        self.rating = None
        self.rerate = rerate
        self.default_rating = kodiUtilities.getSettingAsInt('rating_default')

    def onInit(self):
        s = utilities.getFormattedItemName(self.media_type, self.media)
        self.getControl(10012).setLabel(s)

        rateID = 11029 + self.default_rating
        if self.rerate and self.media['user']['ratings'] and int(self.media['user']['ratings']['rating']) > 0:
            rateID = 11029 + int(self.media['user']['ratings']['rating'])
        self.setFocus(self.getControl(rateID))

    def onClick(self, controlID):
        if controlID in self.buttons:
            self.rating = self.buttons[controlID]
            self.close()

    def onFocus(self, controlID):
        if controlID in self.focus_labels:
            s = kodiUtilities.getString(self.focus_labels[controlID])

            if self.rerate:
                if self.media['user']['ratings'] and self.media['user']['ratings']['rating'] == self.buttons[controlID]:
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
            self.getControl(10013).setLabel('')
