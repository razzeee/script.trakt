# -*- coding: utf-8 -*-
#

import xbmc
import xbmcgui
import xbmcaddon
import json
import re
import logging
from typing import Tuple, List, Dict, Union, Optional
from resources.lib import utilities


# read settings
__addon__ = xbmcaddon.Addon("script.trakt")

logger = logging.getLogger(__name__)

REGEX_URL = "(^https?://)(.+)"


def notification(
    header: str, message: str, time: int = 5000, icon: str = __addon__.getAddonInfo("icon")
) -> None:
    xbmcgui.Dialog().notification(header, message, icon, time)


def showSettings() -> None:
    __addon__.openSettings()


def getSetting(setting: str) -> str:
    return __addon__.getSetting(setting).strip()


def setSetting(setting: str, value: Union[str, int, float, bool]) -> None:
    __addon__.setSetting(setting, str(value))


def getSettingAsBool(setting: str) -> bool:
    return getSetting(setting).lower() == "true"


def getSettingAsFloat(setting: str) -> float:
    try:
        return float(getSetting(setting))
    except ValueError:
        return 0


def getSettingAsInt(setting: str) -> int:
    try:
        return int(getSettingAsFloat(setting))
    except ValueError:
        return 0


def getString(string_id: int) -> str:
    return __addon__.getLocalizedString(string_id)


def kodiJsonRequest(params: Dict) -> Optional[Union[Dict, List]]:
    data = json.dumps(params)
    request = xbmc.executeJSONRPC(data)

    response = json.loads(request)

    try:
        if "result" in response:
            return response["result"]
        return None
    except KeyError:
        logger.warn("[%s] %s" % (params["method"], response["error"]["message"]))
        return None


# check exclusion settings for filename passed as argument


def checkExclusion(fullpath: str) -> bool:
    if not fullpath:
        return True

    # Live TV exclusion
    if fullpath.startswith("pvr://") and getSettingAsBool("ExcludeLiveTV"):
        logger.debug(
            "checkExclusion(): Video is playing via Live TV, which is currently set as excluded location."
        )
        return True

    # HTTP exclusion
    if fullpath.startswith(("http://", "https://")) and getSettingAsBool("ExcludeHTTP"):
        logger.debug(
            "checkExclusion(): Video is playing via HTTP source, which is currently set as excluded location."
        )
        return True

    # Plugin exclusion
    if fullpath.startswith("plugin://") and getSettingAsBool("ExcludePlugin"):
        logger.debug(
            "checkExclusion(): Video is playing via Plugin source, which is currently set as excluded location."
        )
        return True

    # Script exclusion
    if xbmcgui.Window(10000).getProperty(
        "script.trakt.paused"
    ) == "true" and getSettingAsBool("ExcludeScript"):
        logger.debug(
            "checkExclusion(): Video is playing via Script source, which is currently set as excluded location."
        )
        return True

    # Path exclusions
    ExcludePath = getSetting("ExcludePath")
    if ExcludePath != "" and getSettingAsBool("ExcludePathOption"):
        if fullpath.startswith(ExcludePath):
            logger.debug(
                "checkExclusion(): Video is from location, which is currently set as excluded path 1."
            )
            return True

    found = False
    for x in range(2, 13):
        found |= utilities.checkExcludePath(
            getSetting("ExcludePath%i" % x),
            getSettingAsBool("ExcludePathOption%i" % x),
            fullpath,
            x,
        )

    return found


def kodiRpcToTraktMediaObject(type: str, data: Dict, mode: str = "collected") -> Optional[Dict]:
    if type == "show":
        if "uniqueid" in data:
            data["ids"] = data.pop("uniqueid")
        elif "imdbnumber" in data:
            id = data.pop("imdbnumber")
            data["ids"] = utilities.guessBestTraktId(id, type)[0]
        else:
            logger.debug("kodiRpcToTraktMediaObject(): No uniqueid found")
        data["rating"] = (
            data["userrating"] if "userrating" in data and data["userrating"] > 0 else 0
        )
        del data["label"]
        return data
    elif type == "episode":
        if checkExclusion(data["file"]):
            return

        if data["playcount"] is None:
            plays = 0
        else:
            plays = data.pop("playcount")

        if plays > 0:
            watched = 1
        else:
            watched = 0

        episode = {
            "season": data["season"],
            "number": data["episode"],
            "title": data["label"],
            "ids": {"episodeid": data["episodeid"]},
            "watched": watched,
            "plays": plays,
            "collected": 1,
        }

        if "uniqueid" in data:
            if "tmdb" in data["uniqueid"]:
                episode["ids"]["tmdb"] = data["uniqueid"]["tmdb"]
            if "imdb" in data["uniqueid"]:
                episode["ids"]["imdb"] = data["uniqueid"]["imdb"]
            if "tvdb" in data["uniqueid"]:
                episode["ids"]["tvdb"] = data["uniqueid"]["tvdb"]
            elif "unknown" in data["uniqueid"] and data["uniqueid"]["unknown"] != "":
                episode["ids"].update(
                    utilities.guessBestTraktId(data["uniqueid"]["unknown"], type)[0]
                )
        elif "imdbnumber" in data:
            id = data.pop("imdbnumber")
            data["ids"] = utilities.guessBestTraktId(id, type)[0]

        if "lastplayed" in data:
            episode["watched_at"] = utilities.toIso8601DateTime(utilities.fromDateTime(data["lastplayed"]))
        if "dateadded" in data:
            episode["collected_at"] = utilities.toIso8601DateTime(utilities.fromDateTime(data["dateadded"]))
        if "runtime" in data:
            episode["runtime"] = data["runtime"]
        episode["rating"] = (
            data["userrating"] if "userrating" in data and data["userrating"] > 0 else 0
        )
        if mode == "watched" and episode["watched"]:
            return episode
        elif mode == "collected" and episode["collected"]:
            return episode
        else:
            return

    elif type == "movie":
        if checkExclusion(data.pop("file")):
            return
        if "lastplayed" in data:
            data["watched_at"] = utilities.toIso8601DateTime(utilities.fromDateTime(data.pop("lastplayed")))
        if "dateadded" in data:
            data["collected_at"] = utilities.toIso8601DateTime(utilities.fromDateTime(data.pop("dateadded")))
        if data["playcount"] is None:
            data["plays"] = 0
        else:
            data["plays"] = data.pop("playcount")
        data["rating"] = (
            data["userrating"] if "userrating" in data and data["userrating"] > 0 else 0
        )
        data["collected"] = 1  # this is in our kodi so it should be collected
        data["watched"] = 1 if data["plays"] > 0 else 0
        if "uniqueid" in data:
            data["ids"] = data.pop("uniqueid")
        elif "imdbnumber" in data:
            id = data.pop("imdbnumber")
            data["ids"] = utilities.guessBestTraktId(id, type)[0]
        else:
            logger.debug("kodiRpcToTraktMediaObject(): No uniqueid found")
        del data["label"]
        return data
    else:
        logger.debug("kodiRpcToTraktMediaObject() No valid type")
        return


def kodiRpcToTraktMediaObjects(data: Dict, mode: str = "collected") -> Optional[List]:
    if "tvshows" in data:
        shows = data["tvshows"]

        # reformat show array
        for show in shows:
            kodiRpcToTraktMediaObject("show", show, mode)
        return shows

    elif "episodes" in data:
        a_episodes = {}
        seasons = []
        for episode in data["episodes"]:
            while episode["season"] not in a_episodes:
                s_no = episode["season"]
                a_episodes[s_no] = []
            s_no = episode["season"]
            episodeObject = kodiRpcToTraktMediaObject("episode", episode, mode)
            if episodeObject:
                a_episodes[s_no].append(episodeObject)

        for episode in a_episodes:
            seasons.append({"number": episode, "episodes": a_episodes[episode]})
        return seasons

    elif "movies" in data:
        movies = data["movies"]
        kodi_movies = []

        # reformat movie array
        for movie in movies:
            movieObject = kodiRpcToTraktMediaObject("movie", movie, mode)
            if movieObject:
                kodi_movies.append(movieObject)
        return kodi_movies
    else:
        logger.debug("kodiRpcToTraktMediaObjects() No valid key found in rpc data")
        return


def getShowDetailsFromKodi(showID: int, fields: List) -> Optional[Dict]:
    result = kodiJsonRequest(
        {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetTVShowDetails",
            "params": {"tvshowid": showID, "properties": fields},
            "id": 1,
        }
    )
    logger.debug("getShowDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getShowDetailsFromKodi(): Result from Kodi was empty.")
        return None

    try:
        return result["tvshowdetails"]
    except KeyError:
        logger.debug("getShowDetailsFromKodi(): KeyError: result['tvshowdetails']")
        return None


def getSeasonDetailsFromKodi(seasonID: int, fields: List) -> Optional[Dict]:
    result = kodiJsonRequest(
        {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetSeasonDetails",
            "params": {"seasonid": seasonID, "properties": fields},
            "id": 1,
        }
    )
    logger.debug("getSeasonDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getSeasonDetailsFromKodi(): Result from Kodi was empty.")
        return None

    try:
        return result["seasondetails"]
    except KeyError:
        logger.debug("getSeasonDetailsFromKodi(): KeyError: result['seasondetails']")
        return None


# get a single episode from kodi given the id


def getEpisodeDetailsFromKodi(libraryId: int, fields: List) -> Optional[Dict]:
    result = kodiJsonRequest(
        {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetEpisodeDetails",
            "params": {"episodeid": libraryId, "properties": fields},
            "id": 1,
        }
    )
    logger.debug("getEpisodeDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getEpisodeDetailsFromKodi(): Result from Kodi was empty.")
        return None

    show_data = getShowDetailsFromKodi(
        result["episodedetails"]["tvshowid"], ["year", "uniqueid", "imdbnumber"]
    )

    if not show_data:
        logger.debug(
            "getEpisodeDetailsFromKodi(): Result from getShowDetailsFromKodi() was empty."
        )
        return None

    if "uniqueid" in show_data:
        result["episodedetails"]["show_ids"] = show_data["uniqueid"]
    elif "imdbnumber" in show_data:
        result["episodedetails"]["show_ids"] = show_data["imdbnumber"]
    result["episodedetails"]["year"] = show_data["year"]

    try:
        return result["episodedetails"]
    except KeyError:
        logger.debug("getEpisodeDetailsFromKodi(): KeyError: result['episodedetails']")
        return None


# get a single movie from kodi given the id


def getMovieDetailsFromKodi(libraryId: int, fields: List) -> Optional[Dict]:
    result = kodiJsonRequest(
        {
            "jsonrpc": "2.0",
            "method": "VideoLibrary.GetMovieDetails",
            "params": {"movieid": libraryId, "properties": fields},
            "id": 1,
        }
    )
    logger.debug("getMovieDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getMovieDetailsFromKodi(): Result from Kodi was empty.")
        return None

    try:
        return result["moviedetails"]
    except KeyError:
        logger.debug("getMovieDetailsFromKodi(): KeyError: result['moviedetails']")
        return None


def checkAndConfigureProxy() -> Optional[str]:
    proxyActive = kodiJsonRequest(
        {
            "jsonrpc": "2.0",
            "method": "Settings.GetSettingValue",
            "params": {"setting": "network.usehttpproxy"},
            "id": 1,
        }
    )["value"]
    proxyType = kodiJsonRequest(
        {
            "jsonrpc": "2.0",
            "method": "Settings.GetSettingValue",
            "params": {"setting": "network.httpproxytype"},
            "id": 1,
        }
    )["value"]
    proxyOverride = getSettingAsBool("proxy_override")

    if proxyOverride:
        proxyURL = getSetting("proxy_uri")
        proxyPort = getSetting("proxy_port")
        proxyUsername = getSetting("proxy_username")
        proxyPassword = getSetting("proxy_password")
    elif proxyActive and (proxyType == 0):
        proxyURL = kodiJsonRequest(
            {
                "jsonrpc": "2.0",
                "method": "Settings.GetSettingValue",
                "params": {"setting": "network.httpproxyserver"},
                "id": 1,
            }
        )["value"]
        proxyPort = str(
            kodiJsonRequest(
                {
                    "jsonrpc": "2.0",
                    "method": "Settings.GetSettingValue",
                    "params": {"setting": "network.httpproxyport"},
                    "id": 1,
                }
            )["value"]
        )
        proxyUsername = kodiJsonRequest(
            {
                "jsonrpc": "2.0",
                "method": "Settings.GetSettingValue",
                "params": {"setting": "network.httpproxyusername"},
                "id": 1,
            }
        )["value"]
        proxyPassword = kodiJsonRequest(
            {
                "jsonrpc": "2.0",
                "method": "Settings.GetSettingValue",
                "params": {"setting": "network.httpproxypassword"},
                "id": 1,
            }
        )["value"]
    else:
        return None

    if proxyUsername and proxyPassword and proxyURL and proxyPort:
        regexUrl = re.compile(REGEX_URL)
        matchURL = regexUrl.search(proxyURL)
        if matchURL:
            return (
                matchURL.group(1)
                + proxyUsername
                + ":"
                + proxyPassword
                + "@"
                + matchURL.group(2)
                + ":"
                + proxyPort
            )
        else:
            return (
                "http://"
                + proxyUsername
                + ":"
                + proxyPassword
                + "@"
                + proxyURL
                + ":"
                + proxyPort
            )
    elif proxyURL and proxyPort:
        regexUrl = re.compile(REGEX_URL)
        hasScheme = regexUrl.search(proxyURL)
        if hasScheme:
            return proxyURL + ":" + proxyPort
        else:
            return "http://" + proxyURL + ":" + proxyPort
    else:
        return None

    return None


def getMediaType() -> Optional[str]:
    listType = xbmc.getInfoLabel("ListItem.DBTYPE")

    xbmc.log("list item type: %s" % listType, xbmc.LOGINFO)

    if listType == "movie":
        return "movie"
    if listType == "tvshow":
        return "show"
    if listType == "season":
        return "season"
    if listType == "episode":
        return "episode"
    else:
        return None


def getInfoLabelDetails(result: Dict) -> Tuple[str, Dict]:
    type = result["item"]["type"]
    data = {"action": "started"}
    # check type of item
    if "id" not in result["item"] or type == "channel":
        # do a deeper check to see if we have enough data to perform scrobbles
        logger.debug(
            "getInfoLabelDetails - Started playing a non-library file, checking available data."
        )
        season = int(xbmc.getInfoLabel("VideoPlayer.Season") or "-1")
        episode = int(xbmc.getInfoLabel("VideoPlayer.Episode") or "-1")
        showtitle = xbmc.getInfoLabel("VideoPlayer.TVShowTitle") or xbmc.getInfoLabel(
            "VideoPlayer.Title"
        )
        title = xbmc.getInfoLabel("VideoPlayer.EpisodeName")
        year = (
            xbmc.getInfoLabel("VideoPlayer.Year") or utilities.regex_year(showtitle)[1]
        )
        video_ids = xbmcgui.Window(10000).getProperty("script.trakt.ids")
        if video_ids:
            data["video_ids"] = json.loads(video_ids)
        logger.debug(
            "getInfoLabelDetails info - ids: %s, showtitle: %s, Year: %s, Season: %s, Episode: %s"
            % (video_ids, showtitle, year, season, episode)
        )

        if season >= 0 and episode > 0 and (showtitle or video_ids):
            # we have season, episode and either a show title or video_ids, can scrobble this as an episode
            type = "episode"
            data["type"] = "episode"
            data["season"] = season
            data["episode"] = episode
            data["showtitle"] = showtitle
            data["title"] = title or showtitle
            if year.isdigit():
                data["year"] = int(year)
            logger.debug(
                "getInfoLabelDetails - Playing a non-library 'episode' - %s - S%02dE%02d - %s."
                % (data["showtitle"], data["season"], data["episode"], data["title"])
            )
        elif (year or video_ids) and season < 0 and not title:
            # we have a year or video_id and no season/showtitle info, enough for a movie
            type = "movie"
            data["type"] = "movie"
            if year.isdigit():
                data["year"] = int(year)
            data["title"] = utilities.regex_year(showtitle)[0] or showtitle
            logger.debug(
                "getInfoLabelDetails - Playing a non-library 'movie' - %s (%s)."
                % (data["title"], data.get("year", "NaN"))
            )
        elif showtitle or title:
            title, season, episode = utilities.regex_tvshow(title)
            if season < 0 and episode < 0:
                title, season, episode = utilities.regex_tvshow(showtitle)
            data["type"] = "episode"
            data["season"] = season
            data["episode"] = episode
            data["title"] = data["showtitle"] = title or showtitle
            logger.debug(
                "getInfoLabelDetails - Title: %s, showtitle: %s, season: %d, episode: %d"
                % (title, showtitle, season, episode)
            )
        else:
            logger.debug(
                "getInfoLabelDetails - Non-library file, not enough data for scrobbling, skipping."
            )
            return {}, {}
    return type, data
