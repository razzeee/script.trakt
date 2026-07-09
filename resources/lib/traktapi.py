# -*- coding: utf-8 -*-
#
import logging
import os
import socket
import threading
import time
from json import dumps, loads
from typing import Any, Dict, Iterable, List, Optional
import urllib.error
import urllib.parse
import urllib.request

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

# read settings
__addon__ = xbmcaddon.Addon("script.trakt")
__addonversion__ = __addon__.getAddonInfo("version")

logger = logging.getLogger(__name__)


class TraktObject(object):
    def __init__(
        self,
        data: Optional[Dict] = None,
        show: Optional["TraktObject"] = None,
        keys: Optional[List] = None,
    ) -> None:
        self._data = data or {}
        self._keys = keys
        self.show = show
        self.pk = (self._data.get("season"), self._data.get("number"))
        self.episodes = self._build_episodes()

    def _build_episodes(self) -> Dict:
        episodes = {}
        for season in self._data.get("seasons", []) or []:
            for episode in season.get("episodes", []) or []:
                item = dict(episode)
                item.setdefault("season", season.get("number"))
                episodes[item.get("number")] = TraktObject(item, show=self)
        return episodes

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    @property
    def keys(self) -> List:
        if self._keys is not None:
            return self._keys
        return list((self._data.get("ids") or {}).items())

    def to_dict(self) -> Dict:
        return dict(self._data)

    def __repr__(self) -> str:
        return repr(self._data)


class TraktSeason(object):
    def __init__(self, data: Dict) -> None:
        self._data = data
        self.number = data.get("number")
        self.episodes = {}
        for episode in data.get("episodes", []) or []:
            item = dict(episode)
            item.setdefault("season", self.number)
            self.episodes[item.get("number")] = TraktObject(
                item, keys=[(self.number, item.get("number"))]
            )

    def __repr__(self) -> str:
        return repr(self._data)


class TraktClient(object):
    api_url = "https://api.trakt.tv"
    max_retry_after = 60

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        proxy_url: Optional[str] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.proxy_url = proxy_url

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
        authorization: Optional[Dict] = None,
        timeout: int = 30,
        retry: bool = True,
        include_headers: bool = False,
        include_error_code: bool = False,
    ) -> Any:
        url = self.api_url + path
        data = dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id,
            "User-Agent": self.user_agent,
        }
        if authorization and authorization.get("access_token"):
            headers["Authorization"] = "Bearer %s" % authorization["access_token"]

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        opener = urllib.request.build_opener()
        if self.proxy_url:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler(
                    {"http": self.proxy_url, "https": self.proxy_url}
                )
            )

        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                data = loads(raw) if raw else None
                if include_error_code:
                    return data, None
                if include_headers:
                    return data, response.headers
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and retry:
                retry_after = self._retry_after(exc)
                if retry_after is not None:
                    logger.debug(
                        "Trakt rate limit reached: retrying %s %s after %s seconds"
                        % (method, path, retry_after)
                    )
                    time.sleep(retry_after)
                    return self.request(
                        method,
                        path,
                        body,
                        authorization=authorization,
                        timeout=timeout,
                        retry=False,
                        include_headers=include_headers,
                        include_error_code=include_error_code,
                    )
            if exc.code == 401 and authorization and authorization.get("refresh_token"):
                raise
            logger.debug("Trakt request failed: %s %s -> %s" % (method, path, exc.code))
            if include_error_code:
                return None, exc.code
            return None
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            logger.debug("Trakt request failed: %s %s -> %s" % (method, path, exc))
            if include_error_code:
                return None, None
            return None

    def _retry_after(self, exc: urllib.error.HTTPError) -> Optional[int]:
        try:
            retry_after = int(exc.headers.get("Retry-After"))
        except (TypeError, ValueError):
            return None

        if retry_after < 0 or retry_after > self.max_retry_after:
            return None
        return retry_after

    def build_path(self, path: str, params: Optional[Dict] = None) -> str:
        if not params:
            return path
        clean_params = {k: v for k, v in params.items() if v is not None}
        if not clean_params:
            return path
        separator = "&" if "?" in path else "?"
        return "%s%s%s" % (path, separator, urllib.parse.urlencode(clean_params))


class traktAPI(object):
    # Placeholders for build-time injection
    __client_id: str = "TRAKT_CLIENT_ID_PLACEHOLDER"
    __client_secret: str = "TRAKT_CLIENT_SECRET_PLACEHOLDER"
    authorization: Optional[Dict] = None
    authDialog: Optional[deviceAuthDialog.DeviceAuthDialog] = None
    client: Optional[TraktClient] = None

    def __init__(self, force: bool = False) -> None:
        logger.debug("Initializing.")

        proxyURL = checkAndConfigureProxy()

        # Configure
        client_id = os.environ.get("TRAKT_CLIENT_ID")
        client_secret = os.environ.get("TRAKT_CLIENT_SECRET")

        if not client_id or not client_secret:
            client_id = deobfuscate(self.__client_id)
            client_secret = deobfuscate(self.__client_secret)

        user_agent = "Kodi script.trakt/%s" % __addonversion__
        self.client = TraktClient(client_id, client_secret, user_agent, proxyURL)

        if getSetting("authorization") and not force:
            self.authorization = loads(getSetting("authorization"))
        else:
            last_reminder = getSettingAsInt("last_reminder")
            now = int(time.time())
            if last_reminder >= 0 and last_reminder < now - (24 * 60 * 60) or force:
                self.login()

    def login(self) -> None:
        # Request new device code
        if not self.client:
            return

        code = self.client.request(
            "POST",
            "/oauth/device/code",
            {"client_id": self.client.client_id},
            timeout=90,
        )

        if not code:
            logger.debug("Error can not reach trakt")
            notification(getString(32024), getString(32023))
            return

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
        poller = threading.Thread(target=self._poll_device_token, args=(code,))
        poller.daemon = True
        poller.start()

        self.authDialog.doModal()

        del self.authDialog

    def _poll_device_token(self, code: Dict) -> None:
        if not self.client:
            return
        started_at = int(time.time())
        expires_in = code.get("expires_in", 600)
        interval = code.get("interval", 5)
        while int(time.time()) - started_at < expires_in:
            token, error_code = self.client.request(
                "POST",
                "/oauth/device/token",
                {
                    "code": code.get("device_code"),
                    "client_id": self.client.client_id,
                    "client_secret": self.client.client_secret,
                },
                timeout=90,
                include_error_code=True,
            )
            if token and token.get("access_token"):
                self.on_authenticated(token)
                return
            if error_code == 400:
                time.sleep(interval)
                continue
            if error_code == 429:
                interval += 1
                time.sleep(interval)
                continue
            if error_code in (404, 409, 410, 418):
                logger.debug(
                    "Device authentication stopped with status %s" % error_code
                )
                self.on_expired()
                return
            time.sleep(interval)
        self.on_expired()

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
        authorized: bool = False,
        timeout: int = 30,
        include_headers: bool = False,
        retry: bool = True,
    ) -> Any:
        if not self.client:
            return None
        authorization = self.authorization if authorized else None
        try:
            return self.client.request(
                method,
                path,
                body,
                authorization=authorization,
                timeout=timeout,
                retry=retry,
                include_headers=include_headers,
            )
        except urllib.error.HTTPError as exc:
            if (
                exc.code == 401
                and authorized
                and self.authorization
                and self.authorization.get("refresh_token")
            ):
                refreshed = self.client.request(
                    "POST",
                    "/oauth/token",
                    {
                        "refresh_token": self.authorization.get("refresh_token"),
                        "client_id": self.client.client_id,
                        "client_secret": self.client.client_secret,
                        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                        "grant_type": "refresh_token",
                    },
                    timeout=90,
                    retry=False,
                )
                if refreshed:
                    self.on_token_refreshed(refreshed)
                    if not retry:
                        return None
                    return self.client.request(
                        method,
                        path,
                        body,
                        authorization=self.authorization,
                        timeout=timeout,
                        retry=False,
                        include_headers=include_headers,
                    )
            logger.debug("Trakt request failed: %s %s -> %s" % (method, path, exc.code))
            return None

    def _get(
        self,
        path: str,
        authorized: bool = False,
        timeout: int = 30,
        include_headers: bool = False,
        retry: bool = True,
    ) -> Any:
        return self._request(
            "GET",
            path,
            authorized=authorized,
            timeout=timeout,
            include_headers=include_headers,
            retry=retry,
        )

    def _post(
        self,
        path: str,
        body: Dict,
        authorized: bool = True,
        timeout: int = 30,
        retry: bool = True,
    ) -> Any:
        return self._request(
            "POST",
            path,
            body=body,
            authorized=authorized,
            timeout=timeout,
            retry=retry,
        )

    def _get_all_pages(
        self,
        path: str,
        authorized: bool = False,
        timeout: int = 90,
        limit: int = 100,
    ) -> List:
        if not self.client:
            return []

        results = []
        page = 1
        page_count = 1
        while page <= page_count:
            page_path = self.client.build_path(path, {"page": page, "limit": limit})
            response = self._get(
                page_path,
                authorized=authorized,
                timeout=timeout,
                include_headers=True,
            )
            if not response:
                break

            data, headers = response
            if data:
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)

            try:
                page_count = int(headers.get("X-Pagination-Page-Count", page_count))
            except (TypeError, ValueError):
                page_count = page
            page += 1

        return results

    def _get_all_ratings(self, media_type: str) -> List:
        results = []
        for rating in range(1, 11):
            results.extend(
                self._get_all_pages(
                    "/sync/ratings/%s/%s" % (media_type, rating),
                    authorized=True,
                    timeout=90,
                )
            )
        return results

    def _merge_object(
        self, store: Dict, item: Dict, media_key: str, metadata_keys: Iterable[str]
    ) -> None:
        media = dict(item.get(media_key) or item)
        for key in metadata_keys:
            if key in item:
                media[key] = item[key]
        ids = media.get("ids") or {}
        key = ids.get("trakt") or media.get("title") or len(store)
        existing = store.get(key)
        if existing:
            merged = existing.to_dict()
            merged.update(media)
            store[key] = TraktObject(merged)
        else:
            store[key] = TraktObject(media)

    def _merge_show(
        self, store: Dict, item: Dict, metadata_keys: Iterable[str]
    ) -> None:
        show = dict(item.get("show") or item)
        incoming_seasons = item.get("seasons", show.get("seasons", []))
        if item.get("season"):
            season = dict(item["season"])
            for key in metadata_keys:
                if key in item:
                    season[key] = item[key]
            incoming_seasons = [season]
        elif item.get("episode"):
            episode = dict(item["episode"])
            for key in metadata_keys:
                if key in item:
                    episode[key] = item[key]
            incoming_seasons = [
                {"number": episode.get("season"), "episodes": [episode]}
            ]
        else:
            for key in metadata_keys:
                if key in item:
                    show[key] = item[key]
        ids = show.get("ids") or {}
        key = ids.get("trakt") or show.get("title") or len(store)
        existing = store.get(key)
        merged = existing.to_dict() if existing else {}
        merged.update(show)
        merged["seasons"] = self._merge_seasons(
            merged.get("seasons", []), incoming_seasons
        )
        store[key] = TraktObject(merged)

    def _merge_seasons(self, existing: List, incoming: List) -> List:
        seasons = {season.get("number"): dict(season) for season in existing or []}
        for season in incoming or []:
            number = season.get("number")
            merged = seasons.get(number, {"number": number})
            merged["episodes"] = self._merge_episodes(
                merged.get("episodes", []), season.get("episodes", [])
            )
            for key, value in season.items():
                if key != "episodes":
                    merged[key] = value
            seasons[number] = merged
        return list(seasons.values())

    def _merge_episodes(self, existing: List, incoming: List) -> List:
        episodes = {episode.get("number"): dict(episode) for episode in existing or []}
        for episode in incoming or []:
            number = episode.get("number")
            merged = episodes.get(number, {"number": number})
            merged.update(episode)
            episodes[number] = merged
        return list(episodes.values())

    def on_aborted(self) -> None:
        """Triggered when device authentication was aborted (either with `DeviceOAuthPoller.stop()`
        or via the "poll" event)"""

        logger.debug("Authentication aborted")
        if self.authDialog:
            self.authDialog.close()

    def on_authenticated(self, token: Dict) -> None:
        """Triggered when device authentication has been completed

        :param token: Authentication token details
        :type token: dict
        """
        self.authorization = token
        setSetting("authorization", dumps(self.authorization))
        logger.debug("Authentication complete: %r" % token)
        if self.authDialog:
            self.authDialog.close()
        notification(getString(32157), getString(32152), 3000)
        self.updateUser()

    def on_expired(self) -> None:
        """Triggered when the device authentication code has expired"""

        logger.debug("Authentication expired")
        if self.authDialog:
            self.authDialog.close()

    def on_poll(self, callback: Any) -> None:
        """Triggered before each poll

        :param callback: Call with `True` to continue polling, or `False` to abort polling
        :type callback: func
        """

        # Continue polling
        callback(True)

    def on_token_refreshed(self, response: Dict) -> None:
        # OAuth token refreshed, save token for future calls
        self.authorization = response
        setSetting("authorization", dumps(self.authorization))

        logger.debug("Token refreshed")

    def updateUser(self) -> None:
        user = self.getUser()
        if user and "user" in user:
            setSetting("user", user["user"]["username"])
        else:
            setSetting("user", "")

    def scrobbleEpisode(
        self, show: Dict, episode: Dict, percent: float, status: str
    ) -> Optional[Dict]:
        if status not in ("start", "pause", "stop"):
            logger.debug("scrobble() Bad scrobble status")
            return None
        return self._post(
            "/scrobble/%s" % status,
            {"show": show, "episode": episode, "progress": percent},
        )

    def scrobbleMovie(self, movie: Dict, percent: float, status: str) -> Optional[Dict]:
        if status not in ("start", "pause", "stop"):
            logger.debug("scrobble() Bad scrobble status")
            return None
        return self._post(
            "/scrobble/%s" % status, {"movie": movie, "progress": percent}
        )

    def getShowsCollected(self, shows: Dict) -> Dict:
        for item in (
            self._get("/sync/collection/shows", authorized=True, timeout=90) or []
        ):
            self._merge_show(shows, item, ("collected_at",))
        return shows

    def getMoviesCollected(self, movies: Dict) -> Dict:
        for item in self._get_all_pages(
            "/sync/collection/movies", authorized=True, timeout=90
        ):
            self._merge_object(movies, item, "movie", ("collected_at",))
        return movies

    def getShowsWatched(self, shows: Dict) -> Dict:
        for item in self._get("/sync/watched/shows", authorized=True, timeout=90) or []:
            self._merge_show(
                shows, item, ("plays", "last_watched_at", "last_updated_at", "reset_at")
            )
        return shows

    def getMoviesWatched(self, movies: Dict) -> Dict:
        for item in (
            self._get("/sync/watched/movies", authorized=True, timeout=90) or []
        ):
            self._merge_object(
                movies, item, "movie", ("plays", "last_watched_at", "last_updated_at")
            )
        return movies

    def getShowsRated(self, shows: Dict) -> Dict:
        for item in self._get_all_ratings("shows"):
            self._merge_show(shows, item, ("rated_at", "rating"))
        return shows

    def getEpisodesRated(self, shows: Dict) -> Dict:
        for item in self._get_all_ratings("episodes"):
            self._merge_show(shows, item, ("rated_at", "rating"))
        return shows

    def getMoviesRated(self, movies: Dict) -> Dict:
        for item in self._get_all_ratings("movies"):
            self._merge_object(movies, item, "movie", ("rated_at", "rating"))
        return movies

    def addToCollection(self, mediaObject: Dict) -> Optional[Dict]:
        return self._post("/sync/collection", mediaObject)

    def removeFromCollection(self, mediaObject: Dict) -> Optional[Dict]:
        return self._post("/sync/collection/remove", mediaObject)

    def addToHistory(self, mediaObject: Dict) -> Optional[Dict]:
        # don't retry this call; it may cause multiple watches
        return self._request(
            "POST",
            "/sync/history",
            body=mediaObject,
            authorized=True,
            timeout=30,
            retry=False,
        )

    def addToWatchlist(self, mediaObject: Dict) -> Optional[Dict]:
        return self._post("/sync/watchlist", mediaObject)

    def getShowRatingForUser(self, showId: str, idType: str = "tvdb") -> Dict:
        ratings = {}
        self.getShowsRated(ratings)
        return findShowMatchInList(showId, ratings, idType)

    def getSeasonRatingForUser(
        self, showId: str, season: int, idType: str = "tvdb"
    ) -> Dict:
        ratings = {}
        for item in self._get_all_ratings("seasons"):
            self._merge_show(ratings, item, ("rated_at", "rating"))
        return findSeasonMatchInList(showId, season, ratings, idType)

    def getEpisodeRatingForUser(
        self, showId: str, season: int, episode: int, idType: str = "tvdb"
    ) -> Dict:
        ratings = {}
        self.getEpisodesRated(ratings)
        return findEpisodeMatchInList(showId, season, episode, ratings, idType)

    def getMovieRatingForUser(self, movieId: str, idType: str = "imdb") -> Dict:
        ratings = {}
        self.getMoviesRated(ratings)
        return findMovieMatchInList(movieId, ratings, idType)

    # Send a rating to Trakt as mediaObject so we can add the rating
    def addRating(self, mediaObject: Dict) -> Optional[Dict]:
        return self._post("/sync/ratings", mediaObject)

    # Send a rating to Trakt as mediaObject so we can remove the rating
    def removeRating(self, mediaObject: Dict) -> Optional[Dict]:
        return self._post("/sync/ratings/remove", mediaObject)

    def getMoviePlaybackProgress(self) -> List[TraktObject]:
        progressMovies = []
        for item in self._get_all_pages(
            "/sync/playback/movies", authorized=True, timeout=90
        ):
            movie = dict(item.get("movie") or {})
            for key in ("progress", "paused_at", "id"):
                if key in item:
                    movie[key] = item[key]
            progressMovies.append(TraktObject(movie))

        return progressMovies

    def getEpisodePlaybackProgress(self) -> List[TraktObject]:
        progressEpisodes = []
        for item in self._get_all_pages(
            "/sync/playback/episodes", authorized=True, timeout=90
        ):
            show = dict(item.get("show") or {})
            episode = dict(item.get("episode") or {})
            for key in ("progress", "paused_at", "id"):
                if key in item:
                    episode[key] = item[key]
            episode.setdefault("season", episode.get("season") or item.get("season"))
            show["seasons"] = self._merge_seasons(
                show.get("seasons", []),
                [{"number": episode.get("season"), "episodes": [episode]}],
            )
            progressEpisodes.append(TraktObject(show))

        return progressEpisodes

    def getMovieSummary(
        self, movieId: str, extended: Optional[str] = None
    ) -> TraktObject:
        path = "/movies/%s" % urllib.parse.quote(str(movieId), safe="")
        if self.client:
            path = self.client.build_path(path, {"extended": extended})
        result = self._get(path)
        if result is not None:
            result.setdefault("watched", False)
        return TraktObject(result or {})

    def getShowSummary(self, showId: str) -> TraktObject:
        result = self._get("/shows/%s" % urllib.parse.quote(str(showId), safe=""))
        if result is not None:
            result.setdefault("seasons", [])
        return TraktObject(result or {})

    def getShowWithAllEpisodesList(self, showId: str) -> List:
        result = self._get(
            "/shows/%s/seasons?extended=episodes"
            % urllib.parse.quote(str(showId), safe=""),
            timeout=90,
        )
        return [TraktSeason(season) for season in result or []]

    def getEpisodeSummary(
        self, showId: str, season: int, episode: int, extended: Optional[str] = None
    ) -> Any:
        path = "/shows/%s/seasons/%s/episodes/%s" % (
            urllib.parse.quote(str(showId), safe=""),
            season,
            episode,
        )
        if self.client:
            path = self.client.build_path(path, {"extended": extended})
        result = self._get(path)
        if result is not None:
            result.setdefault("season", season)
        return TraktObject(result or {})

    def getIdLookup(self, id: str, id_type: str) -> Optional[List]:
        result = self._get_all_pages(
            "/search/%s/%s"
            % (
                urllib.parse.quote(str(id_type), safe=""),
                urllib.parse.quote(str(id), safe=""),
            ),
            timeout=90,
        )
        return self._wrap_search_results(result)

    def getTextQuery(
        self, query: str, type: str, year: Optional[int]
    ) -> Optional[List]:
        if not self.client:
            return None
        if type not in ("movie", "show", "person"):
            logger.debug(
                "Skipping %s text search; current Trakt API contract only exposes movie, show, and person search"
                % type
            )
            return None
        path = self.client.build_path(
            "/search/%s" % urllib.parse.quote(str(type), safe=""),
            {"query": query, "years": year},
        )
        return self._wrap_search_results(self._get_all_pages(path, timeout=90))

    def getUser(self) -> Optional[Dict]:
        return self._get("/users/settings", authorized=True)

    def _wrap_search_results(self, result: Any) -> Optional[List]:
        if not result:
            return None
        if not isinstance(result, list):
            result = [result]
        wrapped = []
        for item in result:
            if "episode" in item:
                show = TraktObject(item.get("show") or {})
                episode = dict(item.get("episode") or {})
                episode.setdefault("season", episode.get("season"))
                wrapped.append(TraktObject(episode, show=show))
            elif "show" in item:
                wrapped.append(TraktObject(item.get("show") or {}))
            elif "movie" in item:
                wrapped.append(TraktObject(item.get("movie") or {}))
            else:
                wrapped.append(TraktObject(item))
        return wrapped
