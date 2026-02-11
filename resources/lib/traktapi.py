# -*- coding: utf-8 -*-
#
import logging
import os
import time
from json import dumps, loads

import xbmcaddon
from resources.lib import deviceAuthDialog
from resources.lib.kodiUtilities import (
    checkAndConfigureProxy,
    getSetting,
    getSettingAsInt,
    getString,
    notification,
    setSetting,
)
from resources.lib.utilities import (
    findEpisodeMatchInList,
    findMovieMatchInList,
    findSeasonMatchInList,
    findShowMatchInList,
)
from resources.lib.obfuscation import deobfuscate
from trakt import Trakt
from trakt.objects import Movie, Show

# read settings
__addon__ = xbmcaddon.Addon("script.trakt")
__addonversion__ = __addon__.getAddonInfo("version")

logger = logging.getLogger(__name__)


class traktAPI(object):
    # Placeholders for build-time injection
    __client_id = "TRAKT_CLIENT_ID_PLACEHOLDER"
    __client_secret = "TRAKT_CLIENT_SECRET_PLACEHOLDER"

    def __init__(self, force=False):
        logger.debug("Initializing.")

        proxyURL = checkAndConfigureProxy()
        if proxyURL:
            Trakt.http.proxies = {"http": proxyURL, "https": proxyURL}

        # Configure
        client_id = os.environ.get("TRAKT_CLIENT_ID")
        client_secret = os.environ.get("TRAKT_CLIENT_SECRET")

        if not client_id or not client_secret:
            client_id = deobfuscate(self.__client_id)
            client_secret = deobfuscate(self.__client_secret)

        Trakt.configuration.defaults.client(
            id=client_id,
            secret=client_secret,
        )

        user_agent = "Kodi script.trakt/%s" % __addonversion__
        if getattr(Trakt.http, "headers", None) is None:
            Trakt.http.headers = {"User-Agent": user_agent}
        else:
            Trakt.http.headers["User-Agent"] = user_agent

        # Bind event
        Trakt.on("oauth.token_refreshed", self.on_token_refreshed)

        Trakt.configuration.defaults.oauth(refresh=True)

        if getSetting("authorization") and not force:
            self.authorization = loads(getSetting("authorization"))
        else:
            last_reminder = getSettingAsInt("last_reminder")
            now = int(time.time())
            if last_reminder >= 0 and last_reminder < now - (24 * 60 * 60) or force:
                self.login()

    def login(self):
        # Request new device code
        with Trakt.configuration.http(timeout=90):
            code = Trakt["oauth/device"].code()

            if not code:
                logger.debug("Error can not reach trakt")
                notification(getString(32024), getString(32023))
            else:
                # Construct device authentication poller
                poller = (
                    Trakt["oauth/device"]
                    .poll(**code)
                    .on("aborted", self.on_aborted)
                    .on("authenticated", self.on_authenticated)
                    .on("expired", self.on_expired)
                    .on("poll", self.on_poll)
                )

                # Start polling for authentication token
                poller.start(daemon=False)

                logger.debug(
                    'Enter the code "%s" at %s to authenticate your account'
                    % (code.get("user_code"), code.get("verification_url"))
                )

                self.authDialog = deviceAuthDialog.DeviceAuthDialog(
                    "script-trakt-DeviceAuthDialog.xml",
                    __addon__.getAddonInfo("path"),
                    code=code.get("user_code"),
                    url=code.get("verification_url"),
                )
                self.authDialog.doModal()

                del self.authDialog

    def on_aborted(self):
        """Triggered when device authentication was aborted (either with `DeviceOAuthPoller.stop()`
        or via the "poll" event)"""

        logger.debug("Authentication aborted")
        self.authDialog.close()

    def on_authenticated(self, token):
        """Triggered when device authentication has been completed

        :param token: Authentication token details
        :type token: dict
        """
        self.authorization = token
        setSetting("authorization", dumps(self.authorization))
        logger.debug("Authentication complete: %r" % token)
        self.authDialog.close()
        notification(getString(32157), getString(32152), 3000)
        self.updateUser()

    def on_expired(self):
        """Triggered when the device authentication code has expired"""

        logger.debug("Authentication expired")
        self.authDialog.close()

    def on_poll(self, callback):
        """Triggered before each poll

        :param callback: Call with `True` to continue polling, or `False` to abort polling
        :type callback: func
        """

        # Continue polling
        callback(True)

    def on_token_refreshed(self, response):
        # OAuth token refreshed, save token for future calls
        self.authorization = response
        setSetting("authorization", dumps(self.authorization))

        logger.debug("Token refreshed")

    def updateUser(self):
        user = self.getUser()
        if user and "user" in user:
            setSetting("user", user["user"]["username"])
        else:
            setSetting("user", "")

    def scrobbleEpisode(self, show, episode, percent, status):
        result = None

        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                if status == "start":
                    result = Trakt["scrobble"].start(
                        show=show, episode=episode, progress=percent
                    )
                elif status == "pause":
                    result = Trakt["scrobble"].pause(
                        show=show, episode=episode, progress=percent
                    )
                elif status == "stop":
                    result = Trakt["scrobble"].stop(
                        show=show, episode=episode, progress=percent
                    )
                else:
                    logger.debug("scrobble() Bad scrobble status")
        return result

    def scrobbleMovie(self, movie, percent, status):
        result = None

        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                if status == "start":
                    result = Trakt["scrobble"].start(movie=movie, progress=percent)
                elif status == "pause":
                    result = Trakt["scrobble"].pause(movie=movie, progress=percent)
                elif status == "stop":
                    result = Trakt["scrobble"].stop(movie=movie, progress=percent)
                else:
                    logger.debug("scrobble() Bad scrobble status")
        return result

    def getShowsCollected(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/collection"].shows(shows, exceptions=True)
        return shows

    def getMoviesCollected(self, movies):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/collection"].movies(movies, exceptions=True)
        return movies

    def getShowsWatched(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/watched"].shows(shows, exceptions=True)
        return shows

    def getMoviesWatched(self, movies):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/watched"].movies(movies, exceptions=True)
        return movies

    def getShowsRated(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/ratings"].shows(store=shows, exceptions=True)
        return shows

    def getEpisodesRated(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/ratings"].episodes(store=shows, exceptions=True)
        return shows

    def getMoviesRated(self, movies):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt["sync/ratings"].movies(store=movies, exceptions=True)
        return movies

    def addToCollection(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt["sync/collection"].add(mediaObject)
        return result

    def removeFromCollection(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt["sync/collection"].remove(mediaObject)
        return result

    def addToHistory(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            # don't try this call it may cause multiple watches
            result = Trakt["sync/history"].add(mediaObject)
        return result

    def addToWatchlist(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt["sync/watchlist"].add(mediaObject)
        return result

    def getShowRatingForUser(self, showId, idType="tvdb"):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt["sync/ratings"].shows(store=ratings)
        return findShowMatchInList(showId, ratings, idType)

    def getSeasonRatingForUser(self, showId, season, idType="tvdb"):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt["sync/ratings"].seasons(store=ratings)
        return findSeasonMatchInList(showId, season, ratings, idType)

    def getEpisodeRatingForUser(self, showId, season, episode, idType="tvdb"):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt["sync/ratings"].episodes(store=ratings)
        return findEpisodeMatchInList(showId, season, episode, ratings, idType)

    def getMovieRatingForUser(self, movieId, idType="imdb"):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt["sync/ratings"].movies(store=ratings)
        return findMovieMatchInList(movieId, ratings, idType)

    # Send a rating to Trakt as mediaObject so we can add the rating
    def addRating(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt["sync/ratings"].add(mediaObject)
        return result

    # Send a rating to Trakt as mediaObject so we can remove the rating
    def removeRating(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt["sync/ratings"].remove(mediaObject)
        return result

    def getMoviePlaybackProgress(self):
        progressMovies = []

        # Fetch playback
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                playback = Trakt["sync/playback"].movies(exceptions=True)

                for _, item in list(playback.items()):
                    if type(item) is Movie:
                        progressMovies.append(item)

        return progressMovies

    def getEpisodePlaybackProgress(self):
        progressEpisodes = []

        # Fetch playback
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                playback = Trakt["sync/playback"].episodes(exceptions=True)

                for _, item in list(playback.items()):
                    if type(item) is Show:
                        progressEpisodes.append(item)

        return progressEpisodes

    def getMovieSummary(self, movieId, extended=None):
        with Trakt.configuration.http(retry=True):
            return Trakt["movies"].get(movieId, extended=extended)

    def getShowSummary(self, showId):
        with Trakt.configuration.http(retry=True):
            return Trakt["shows"].get(showId)

    def getShowWithAllEpisodesList(self, showId):
        with Trakt.configuration.http(retry=True, timeout=90):
            return Trakt["shows"].seasons(showId, extended="episodes")

    def getEpisodeSummary(self, showId, season, episode, extended=None):
        with Trakt.configuration.http(retry=True):
            return Trakt["shows"].episode(showId, season, episode, extended=extended)

    def getIdLookup(self, id, id_type):
        with Trakt.configuration.http(retry=True):
            result = Trakt["search"].lookup(id, id_type)
            if result and not isinstance(result, list):
                result = [result]
            return result

    def getTextQuery(self, query, type, year):
        with Trakt.configuration.http(retry=True, timeout=90):
            result = Trakt["search"].query(query, type, year)
            if result and not isinstance(result, list):
                result = [result]
            return result

    def getUser(self):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt["users/settings"].get()
                return result
