# -*- coding: utf-8 -*-
#
import xbmcaddon
import logging
from trakt import Trakt, ClientError, ServerError
from trakt.objects import Movie, Episode, Show
from utilities import findMovieMatchInList, findShowMatchInList, findEpisodeMatchInList, findSeasonMatchInList, createError
from kodiUtilities import getSetting, setSetting, notification, getString, checkAndConfigureProxy
from sys import version_info

if version_info >= (2, 7):
    from json import loads, dumps
else:
    from simplejson import loads, dumps

# read settings
__addon__ = xbmcaddon.Addon('script.trakt')
__addonversion__ = __addon__.getAddonInfo('version')

logger = logging.getLogger(__name__)

class traktAPI(object):
    __client_id = "d4161a7a106424551add171e5470112e4afdaf2438e6ef2fe0548edc75924868"
    __client_secret = "b5fcd7cb5d9bb963784d11bbf8535bc0d25d46225016191eb48e50792d2155c0"

    def __init__(self):
        logger.debug("Initializing.")

        proxyURL = checkAndConfigureProxy()
        if proxyURL:
            Trakt.http.proxies = {
                'http': proxyURL,
                'https': proxyURL
            }
        
        if getSetting('authorization'):
            self.authorization = loads(getSetting('authorization'))
        else:
            self.authorization = {}

        # Bind trakt events
        Trakt.on('oauth.token_refreshed', self.on_token_refreshed)

        Trakt.configuration.defaults.app(
            id=999
        )

        # Configure
        Trakt.configuration.defaults.client(
            id=self.__client_id,
            secret=self.__client_secret
        )

        #Set defaults
        Trakt.configuration.defaults.oauth(
            refresh=True
        )

    def authenticate(self, pin=None):
        # Attempt authentication (retrieve new token)
        with Trakt.configuration.http(retry=True):
            try:
                # Exchange `code` for `access_token`
                logger.debug("Exchanging pin for access token")
                self.authorization = Trakt['oauth'].token_exchange(pin, 'urn:ietf:wg:oauth:2.0:oob')

                if not self.authorization:
                    logger.debug("Authentication Failure")
                    return False
                else:
                    setSetting('authorization', dumps(self.authorization))
                    return True
            except Exception as ex:
                message = createError(ex)
                logger.fatal(message)
                logger.debug("Cannot connect to server")
                notification('Trakt', getString(32023))

    def on_token_refreshed(self, response):
        # OAuth token refreshed, save token for future calls
        self.authorization = response
        setSetting('authorization', dumps(self.authorization))

        logger.debug('Token refreshed')

    # helper for onSettingsChanged
    def updateSettings(self):
        if getSetting('authorization'):
            _auth = loads(getSetting('authorization'))
        else:
            _auth = {}

        if self.authorization != _auth:
            self.authorization = _auth
            user = self.getUser()
            if user and 'user' in user:
                setSetting('user', user['user']['username'])
            else:
                setSetting('user', '')

    def scrobbleEpisode(self, show, episode, percent, status):
        result = None

        with Trakt.configuration.oauth.from_response(self.authorization):
            if status == 'start':
                with Trakt.configuration.http(retry=True):
                    result = Trakt['scrobble'].start(
                        show=show,
                        episode=episode,
                        progress=percent)
            elif status == 'pause':
                with Trakt.configuration.http(retry=True):
                    result = Trakt['scrobble'].pause(
                        show=show,
                        episode=episode,
                        progress=percent)
            elif status == 'stop':
                #don't retry on stop, this will cause multiple scrobbles
                result = Trakt['scrobble'].stop(
                    show=show,
                    episode=episode,
                    progress=percent)
            else:
                    logger.debug("scrobble() Bad scrobble status")
        return result

    def scrobbleMovie(self, movie, percent, status):
        result = None

        with Trakt.configuration.oauth.from_response(self.authorization):
            if status == 'start':
                with Trakt.configuration.http(retry=True):
                    result = Trakt['scrobble'].start(
                        movie=movie,
                        progress=percent)
            elif status == 'pause':
                with Trakt.configuration.http(retry=True):
                    result = Trakt['scrobble'].pause(
                        movie=movie,
                        progress=percent)
            elif status == 'stop':
                #don't retry on stop, this will cause multiple scrobbles
                result = Trakt['scrobble'].stop(
                    movie=movie,
                    progress=percent)
            else:
                logger.debug("scrobble() Bad scrobble status")
        return result

    def getShowsCollected(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/collection'].shows(shows, exceptions=True)
        return shows

    def getMoviesCollected(self, movies):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/collection'].movies(movies, exceptions=True)
        return movies

    def getShowsWatched(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/watched'].shows(shows, exceptions=True)
        return shows

    def getMoviesWatched(self, movies):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/watched'].movies(movies, exceptions=True)
        return movies

    def getShowsRated(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/ratings'].shows(shows, exceptions=True)
        return shows

    def getEpisodesRated(self, shows):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/ratings'].episodes(shows, exceptions=True)
        return shows

    def getMoviesRated(self, movies):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True, timeout=90):
                Trakt['sync/ratings'].movies(movies, exceptions=True)
        return movies

    def addToCollection(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt['sync/collection'].add(mediaObject)
        return result

    def removeFromCollection(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt['sync/collection'].remove(mediaObject)
        return result

    def addToHistory(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            #don't try this call it may cause multiple watches
            result = Trakt['sync/history'].add(mediaObject)
        return result

    def addToWatchlist(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt['sync/watchlist'].add(mediaObject)
        return result

    def getShowRatingForUser(self, showId, idType='tvdb'):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt['sync/ratings'].shows(ratings)
        return findShowMatchInList(showId, ratings, idType)

    def getSeasonRatingForUser(self, showId, season, idType='tvdb'):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt['sync/ratings'].seasons(ratings)
        return findSeasonMatchInList(showId, season, ratings, idType)

    def getEpisodeRatingForUser(self, showId, season, episode, idType='tvdb'):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt['sync/ratings'].episodes(ratings)
        return findEpisodeMatchInList(showId, season, episode, ratings, idType)

    def getMovieRatingForUser(self, movieId, idType='imdb'):
        ratings = {}
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                Trakt['sync/ratings'].movies(ratings)
        return findMovieMatchInList(movieId, ratings, idType)

    # Send a rating to Trakt as mediaObject so we can add the rating
    def addRating(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt['sync/ratings'].add(mediaObject)
        return result

    # Send a rating to Trakt as mediaObject so we can remove the rating
    def removeRating(self, mediaObject):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt['sync/ratings'].remove(mediaObject)
        return result

    def getMoviePlaybackProgress(self):
        progressMovies = []

        # Fetch playback
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                playback = Trakt['sync/playback'].movies(exceptions=True)

                for _, item in playback.items():
                    if type(item) is Movie:
                        progressMovies.append(item)

        return progressMovies

    def getEpisodePlaybackProgress(self):
        progressEpisodes = []

        # Fetch playback
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                playback = Trakt['sync/playback'].episodes(exceptions=True)

                for _, item in playback.items():
                    if type(item) is Show:
                        progressEpisodes.append(item)

        return progressEpisodes

    def getMovieSummary(self, movieId):
        with Trakt.configuration.http(retry=True):
            return Trakt['movies'].get(movieId)

    def getShowSummary(self, showId):
        with Trakt.configuration.http(retry=True):
            return Trakt['shows'].get(showId)

    def getEpisodeSummary(self, showId, season, episode):
        with Trakt.configuration.http(retry=True):
            return Trakt['shows'].episode(showId, season, episode)

    def getIdLookup(self, id, id_type):
        with Trakt.configuration.http(retry=True):
            result = Trakt['search'].lookup(id, id_type)
            if result and not isinstance(result, list):
                result = [result]
            return result

    def getUser(self):
        with Trakt.configuration.oauth.from_response(self.authorization):
            with Trakt.configuration.http(retry=True):
                result = Trakt['users/settings'].get()
                return result