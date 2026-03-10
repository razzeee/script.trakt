# -*- coding: utf-8 -*-
#

import xbmc
import time
import logging
from typing import Dict, List, Optional, Any
from resources.lib import utilities
from resources.lib import kodiUtilities
import math
from resources.lib.rating import ratingCheck

logger = logging.getLogger(__name__)


class Scrobbler:
    traktapi: Any = None
    isPlaying: bool = False
    isPaused: bool = False
    stopScrobbler: bool = False
    isPVR: bool = False
    isMultiPartEpisode: bool = False
    lastMPCheck: float = 0
    curMPEpisode: int = 0
    videoDuration: float = 1
    watchedTime: float = 0
    pausedAt: float = 0
    curVideo: Optional[Dict] = None
    curVideoInfo: Optional[Dict] = None
    playlistIndex: int = 0
    traktShowSummary: Optional[Dict] = None
    videosToRate: List[Dict] = []

    def __init__(self, api: Any) -> None:
        self.traktapi = api

    def _currentEpisode(self, watchedPercent: float, episodeCount: int) -> int:
        split = 100 / episodeCount
        for i in range(episodeCount - 1, 0, -1):
            if watchedPercent >= (i * split):
                return i
        return 0

    def transitionCheck(self, isSeek: bool = False) -> None:
        if not xbmc.Player().isPlayingVideo():
            return

        if self.isPlaying:
            t = xbmc.Player().getTime()
            position = xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition()
            if self.isPVR:
                if self.stopScrobbler:
                    self.stopScrobbler = False
                    self.lastMPCheck = time.time() + 600  # 10min transition sleep
                    self.__scrobble("stop")
                    return
                self.watchedTime = utilities._to_sec(
                    xbmc.getInfoLabel("PVR.EpgEventElapsedTime(hh:mm:ss)")
                )
                self.videoDuration = int(
                    utilities._to_sec(
                        xbmc.getInfoLabel("PVR.EpgEventDuration(hh:mm:ss)")
                    )
                )
            elif self.playlistIndex == position:
                self.watchedTime = t
            else:
                logger.debug(
                    "Current playlist item changed! Not updating time! (%d -> %d)"
                    % (self.playlistIndex, position)
                )

            # do transition check every minute
            if (time.time() > (self.lastMPCheck + 60)) or isSeek:
                self.lastMPCheck = time.time()
                watchedPercent = self.__calculateWatchedPercent()

                if "id" in self.curVideo and self.isMultiPartEpisode:
                    epIndex = self._currentEpisode(
                        watchedPercent, self.curVideo["multi_episode_count"]
                    )
                    if self.curMPEpisode != epIndex:
                        response = self.__scrobble("stop")
                        if response is not None:
                            logger.debug("Scrobble response: %s" % str(response))
                            self.videosToRate.append(self.curVideoInfo)
                            # update current information
                            self.curMPEpisode = epIndex
                            self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject(
                                "episode",
                                kodiUtilities.getEpisodeDetailsFromKodi(
                                    self.curVideo["multi_episode_data"][
                                        self.curMPEpisode
                                    ],
                                    [
                                        "showtitle",
                                        "season",
                                        "episode",
                                        "tvshowid",
                                        "uniqueid",
                                        "file",
                                        "playcount",
                                    ],
                                ),
                            )

                            logger.debug(
                                "Multi episode transition - call start for next episode"
                            )
                            response = self.__scrobble("start")
                            self.__preFetchUserRatings(response)

                elif self.isPVR:
                    activePlayers = kodiUtilities.kodiJsonRequest(
                        {"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1}
                    )
                    logger.debug("Scrobble - activePlayers: %s" % activePlayers)
                    playerId = int(activePlayers[0]["playerid"])
                    logger.debug("Scrobble - Doing Player.GetItem kodiJsonRequest")
                    result = kodiUtilities.kodiJsonRequest(
                        {
                            "jsonrpc": "2.0",
                            "method": "Player.GetItem",
                            "params": {"playerid": playerId},
                            "id": 1,
                        }
                    )
                    if result:
                        logger.debug("Scrobble - %s" % result)
                        type, curVideo = kodiUtilities.getInfoLabelDetails(result)
                        if curVideo != self.curVideo:
                            response = self.__scrobble("stop")
                            if response is not None:
                                logger.debug("Scrobble response: %s" % str(response))
                                logger.debug("Scrobble PVR transition")
                                # update current information
                                self.curVideo = curVideo
                                if utilities.isMovie(self.curVideo["type"]):
                                    if (
                                        "title" in self.curVideo
                                        and "year" in self.curVideo
                                    ):
                                        self.curVideoInfo = {
                                            "title": self.curVideo["title"],
                                            "year": self.curVideo["year"],
                                        }
                                    else:
                                        logger.debug(
                                            "Scrobble Couldn't set curVideoInfo for movie type"
                                        )
                                    logger.debug(
                                        "Scrobble Movie type, curVideoInfo: %s"
                                        % self.curVideoInfo
                                    )

                                elif utilities.isEpisode(self.curVideo["type"]):
                                    if (
                                        "title" in self.curVideo
                                        and "season" in self.curVideo
                                        and "episode" in self.curVideo
                                    ):
                                        self.curVideoInfo = {
                                            "title": self.curVideo["title"],
                                            "season": self.curVideo["season"],
                                            "number": self.curVideo["episode"],
                                        }

                                        title, year = utilities.regex_year(
                                            self.curVideo["showtitle"]
                                        )
                                        if not year:
                                            self.traktShowSummary = {
                                                "title": self.curVideo["showtitle"]
                                            }
                                        else:
                                            self.traktShowSummary = {
                                                "title": title,
                                                "year": year,
                                            }

                                        if "year" in self.curVideo:
                                            self.traktShowSummary[
                                                "year"
                                            ] = self.curVideo["year"]
                                else:
                                    logger.debug(
                                        "Scrobble Couldn't set curVideoInfo/traktShowSummary for episode type"
                                    )
                                logger.debug(
                                    "Scrobble Episode type, curVideoInfo: %s"
                                    % self.curVideoInfo
                                )
                                logger.debug(
                                    "Scrobble Episode type, traktShowSummary: %s"
                                    % self.traktShowSummary
                                )
                                response = self.__scrobble("start")

                elif isSeek:
                    self.__scrobble("start")

    def playbackStarted(self, data: Dict) -> None:
        logger.debug("playbackStarted(data: %s)" % data)
        if not data:
            return
        self.curVideo = data
        self.curVideoInfo = None
        self.videosToRate = []

        if (
            not kodiUtilities.getSettingAsBool("scrobble_fallback")
            and "id" not in self.curVideo
            and "video_ids" not in self.curVideo
        ):
            logger.debug("Aborting scrobble to avoid fallback: %s" % (self.curVideo))
            return

        if "type" in self.curVideo:
            logger.debug("Watching: %s" % self.curVideo["type"])
            if not xbmc.Player().isPlayingVideo():
                logger.debug("Suddenly stopped watching item")
                return
            # Wait for possible silent seek (caused by resuming)
            xbmc.sleep(1000)
            try:
                self.isPVR = xbmc.getCondVisibility(
                    "Pvr.IsPlayingTv"
                ) | xbmc.Player().getPlayingFile().startswith("pvr://")
                self.watchedTime = xbmc.Player().getTime()
                self.videoDuration = 0
                if self.isPVR:
                    self.watchedTime = utilities._to_sec(
                        xbmc.getInfoLabel("PVR.EpgEventElapsedTime(hh:mm:ss)")
                    )
                    self.videoDuration = int(
                        utilities._to_sec(
                            xbmc.getInfoLabel("PVR.EpgEventDuration(hh:mm:ss)")
                        )
                    )
                else:
                    self.videoDuration = xbmc.Player().getTotalTime()
            except Exception as e:
                logger.debug("Suddenly stopped watching item: %s" % e.message)
                self.curVideo = None
                return

            if self.videoDuration == 0:
                if utilities.isMovie(self.curVideo["type"]):
                    self.videoDuration = 90
                elif utilities.isEpisode(self.curVideo["type"]):
                    self.videoDuration = 30
                else:
                    self.videoDuration = 1

            self.playlistIndex = xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition()

            self.isMultiPartEpisode = False
            if utilities.isMovie(self.curVideo["type"]):
                if "id" in self.curVideo:
                    self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject(
                        "movie",
                        kodiUtilities.getMovieDetailsFromKodi(
                            self.curVideo["id"],
                            [
                                "uniqueid",
                                "imdbnumber",
                                "title",
                                "year",
                                "file",
                                "lastplayed",
                                "playcount",
                            ],
                        ),
                    )
                elif "video_ids" in self.curVideo:
                    self.curVideoInfo = {"ids": self.curVideo["video_ids"]}
                elif "title" in self.curVideo and "year" in self.curVideo:
                    self.curVideoInfo = {
                        "title": self.curVideo["title"],
                        "year": self.curVideo["year"],
                    }
                else:
                    logger.debug("Couldn't set curVideoInfo for movie type")
                logger.debug("Movie type, curVideoInfo: %s" % self.curVideoInfo)

            elif utilities.isEpisode(self.curVideo["type"]):
                if "id" in self.curVideo:
                    episodeDetailsKodi = kodiUtilities.getEpisodeDetailsFromKodi(
                        self.curVideo["id"],
                        [
                            "showtitle",
                            "season",
                            "episode",
                            "tvshowid",
                            "uniqueid",
                            "file",
                            "playcount",
                        ],
                    )
                    title, year = utilities.regex_year(episodeDetailsKodi["showtitle"])
                    if not year:
                        self.traktShowSummary = {
                            "title": episodeDetailsKodi["showtitle"],
                            "year": episodeDetailsKodi["year"],
                        }
                    else:
                        self.traktShowSummary = {"title": title, "year": year}
                    if "show_ids" in episodeDetailsKodi:
                        self.traktShowSummary["ids"] = episodeDetailsKodi["show_ids"]
                    self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject(
                        "episode", episodeDetailsKodi
                    )
                    if not self.curVideoInfo:  # getEpisodeDetailsFromKodi was empty
                        logger.debug(
                            "Episode details from Kodi was empty, ID (%d) seems invalid, aborting further scrobbling of this episode."
                            % self.curVideo["id"]
                        )
                        self.curVideo = None
                        self.isPlaying = False
                        self.watchedTime = 0
                        return
                elif (
                    "video_ids" in self.curVideo
                    and "season" in self.curVideo
                    and "episode" in self.curVideo
                ):
                    self.curVideoInfo = {
                        "season": self.curVideo["season"],
                        "number": self.curVideo["episode"],
                    }
                    self.traktShowSummary = {"ids": self.curVideo["video_ids"]}
                elif (
                    "title" in self.curVideo
                    and "season" in self.curVideo
                    and "episode" in self.curVideo
                ):
                    self.curVideoInfo = {
                        "title": self.curVideo["title"],
                        "season": self.curVideo["season"],
                        "number": self.curVideo["episode"],
                    }

                    title, year = utilities.regex_year(self.curVideo["showtitle"])
                    if not year:
                        self.traktShowSummary = {"title": self.curVideo["showtitle"]}
                    else:
                        self.traktShowSummary = {"title": title, "year": year}

                    if "year" in self.curVideo:
                        self.traktShowSummary["year"] = self.curVideo["year"]
                else:
                    logger.debug(
                        "Couldn't set curVideoInfo/traktShowSummary for episode type"
                    )

                if (
                    "multi_episode_count" in self.curVideo
                    and self.curVideo["multi_episode_count"] > 1
                ):
                    self.isMultiPartEpisode = True

                logger.debug("Episode type, curVideoInfo: %s" % self.curVideoInfo)
                logger.debug(
                    "Episode type, traktShowSummary: %s" % self.traktShowSummary
                )

            self.isPlaying = True
            self.isPaused = False

            result = {}
            if kodiUtilities.getSettingAsBool(
                "scrobble_movie"
            ) or kodiUtilities.getSettingAsBool("scrobble_episode"):
                result = self.__scrobble("start")
            elif (
                kodiUtilities.getSettingAsBool("rate_movie")
                and utilities.isMovie(self.curVideo["type"])
                and "ids" in self.curVideoInfo
            ):
                best_id, id_type = utilities.best_id(
                    self.curVideoInfo["ids"], self.curVideo["type"]
                )
                result = {"movie": self.traktapi.getMovieSummary(best_id).to_dict()}
            elif (
                kodiUtilities.getSettingAsBool("rate_episode")
                and utilities.isEpisode(self.curVideo["type"])
                and "ids" in self.traktShowSummary
            ):
                best_id, id_type = utilities.best_id(
                    self.traktShowSummary["ids"], self.curVideo["type"]
                )
                result = {
                    "show": self.traktapi.getShowSummary(best_id).to_dict(),
                    "episode": self.traktapi.getEpisodeSummary(
                        best_id,
                        self.curVideoInfo["season"],
                        self.curVideoInfo["number"],
                    ).to_dict(),
                }
                result["episode"]["season"] = self.curVideoInfo["season"]

            if "id" in self.curVideo:
                if utilities.isMovie(self.curVideo["type"]):
                    result["movie"]["movieid"] = self.curVideo["id"]
                elif utilities.isEpisode(self.curVideo["type"]):
                    result["episode"]["episodeid"] = self.curVideo["id"]

            self.__preFetchUserRatings(result)

    def __preFetchUserRatings(self, result: Dict) -> None:
        if result:
            if utilities.isMovie(
                self.curVideo["type"]
            ) and kodiUtilities.getSettingAsBool("rate_movie"):
                # pre-get summary information, for faster rating dialog.
                logger.debug(
                    "Movie rating is enabled, pre-fetching summary information."
                )
                self.curVideoInfo = result["movie"]
                self.curVideoInfo["user"] = {
                    "ratings": self.traktapi.getMovieRatingForUser(
                        result["movie"]["ids"]["trakt"], "trakt"
                    )
                }
            elif utilities.isEpisode(
                self.curVideo["type"]
            ) and kodiUtilities.getSettingAsBool("rate_episode"):
                # pre-get summary information, for faster rating dialog.
                logger.debug(
                    "Episode rating is enabled, pre-fetching summary information."
                )
                self.curVideoInfo = result["episode"]
                self.curVideoInfo["user"] = {
                    "ratings": self.traktapi.getEpisodeRatingForUser(
                        result["show"]["ids"]["trakt"],
                        self.curVideoInfo["season"],
                        self.curVideoInfo["number"],
                        "trakt",
                    )
                }
            logger.debug("Pre-Fetch result: %s; Info: %s" % (result, self.curVideoInfo))

    def playbackResumed(self) -> None:
        if not self.isPlaying or self.isPVR:
            return

        logger.debug("playbackResumed()")
        if self.isPaused:
            p = time.time() - self.pausedAt
            logger.debug("Resumed after: %s" % str(p))
            self.pausedAt = 0
            self.isPaused = False
            self.__scrobble("start")

    def playbackPaused(self) -> None:
        if not self.isPlaying or self.isPVR:
            return

        logger.debug("playbackPaused()")
        logger.debug("Paused after: %s" % str(self.watchedTime))
        self.isPaused = True
        self.pausedAt = time.time()
        self.__scrobble("pause")

    def playbackSeek(self) -> None:
        if not self.isPlaying:
            return

        logger.debug("playbackSeek()")
        self.transitionCheck(isSeek=True)

    def playbackEnded(self) -> None:
        if not self.isPVR:
            self.videosToRate.append(self.curVideoInfo)
        if not self.isPlaying:
            return

        logger.debug("playbackEnded()")
        if not self.videosToRate and not self.isPVR:
            logger.debug("Warning: Playback ended but video forgotten.")
            return
        self.isPlaying = False
        self.stopScrobbler = False
        if self.watchedTime != 0:
            if "type" in self.curVideo:
                self.__scrobble("stop")
                ratingCheck(
                    self.curVideo["type"],
                    self.videosToRate,
                    self.watchedTime,
                    self.videoDuration,
                )
            self.watchedTime = 0
            self.isPVR = False
            self.isMultiPartEpisode = False
        self.videosToRate = []
        self.curVideoInfo = None
        self.curVideo = None
        self.playlistIndex = 0

    def __calculateWatchedPercent(self) -> float:
        # we need to floor this, so this calculation yields the same result as the playback progress calculation
        floored = math.floor(self.videoDuration)
        if floored != 0:
            return (self.watchedTime / floored) * 100
        else:
            return 0

    def __scrobble(self, status: str) -> Optional[Dict]:
        if not self.curVideoInfo:
            return

        logger.debug("scrobble()")
        scrobbleMovieOption = kodiUtilities.getSettingAsBool("scrobble_movie")
        scrobbleEpisodeOption = kodiUtilities.getSettingAsBool("scrobble_episode")

        watchedPercent = self.__calculateWatchedPercent()
        if utilities.isMovie(self.curVideo["type"]) and scrobbleMovieOption:
            response = self.traktapi.scrobbleMovie(
                self.curVideoInfo, watchedPercent, status
            )
            if response is not None:
                self.__scrobbleNotification(response)
                logger.debug("Scrobble response: %s" % str(response))
                return response
            else:
                logger.debug(
                    "Failed to scrobble movie: %s | %s | %s"
                    % (self.curVideoInfo, watchedPercent, status)
                )

        elif utilities.isEpisode(self.curVideo["type"]) and scrobbleEpisodeOption:
            if self.isMultiPartEpisode:
                logger.debug(
                    "Multi-part episode, scrobbling part %d of %d."
                    % (self.curMPEpisode + 1, self.curVideo["multi_episode_count"])
                )
                adjustedDuration = int(
                    self.videoDuration / self.curVideo["multi_episode_count"]
                )
                watchedPercent = (
                    (self.watchedTime - (adjustedDuration * self.curMPEpisode))
                    / adjustedDuration
                ) * 100

            logger.debug(
                "scrobble sending show object: %s" % str(self.traktShowSummary)
            )
            logger.debug("scrobble sending episode object: %s" % str(self.curVideoInfo))
            response = self.traktapi.scrobbleEpisode(
                self.traktShowSummary, self.curVideoInfo, watchedPercent, status
            )

            if kodiUtilities.getSettingAsBool("scrobble_secondary_title"):
                logger.debug(
                    "[traktPlayer] Setting is enabled to try secondary show title, if necessary."
                )
                # If there is an empty response, the reason might be that the title we have isn't the actual show title,
                # but rather an alternative title. To handle this case, call the Trakt search function.
                if response is None:
                    logger.debug(
                        "Searching for show title: %s" % self.traktShowSummary["title"]
                    )
                    # This text query API is basically the same as searching on the website. Works with alternative
                    # titles, unlike the scrobble function.
                    newResp = self.traktapi.getTextQuery(
                        self.traktShowSummary["title"], "show", None
                    )
                    if not newResp:
                        logger.debug("Empty Response from getTextQuery, giving up")
                    else:
                        logger.debug(
                            "Got Response from getTextQuery: %s" % str(newResp)
                        )
                        # We got something back. Have to assume the first show found is the right one; if there's more than
                        # one, there's no way to know which to use. Pull the primary title from the response (and the year,
                        # just because it's there).
                        showObj = {"title": newResp[0].title, "year": newResp[0].year}
                        logger.debug(
                            "scrobble sending getTextQuery first show object: %s"
                            % str(showObj)
                        )
                        # Now we can attempt the scrobble again, using the primary title this time.
                        response = self.traktapi.scrobbleEpisode(
                            showObj, self.curVideoInfo, watchedPercent, status
                        )

            if response is not None:
                # Don't scrobble incorrect episode, episode numbers can differ from database. ie Aired vs. DVD order. Use fuzzy logic to match episode title.
                if self.isPVR and not utilities._fuzzyMatch(
                    self.curVideoInfo["title"], response["episode"]["title"], 50.0
                ):
                    logger.debug(
                        "scrobble sending incorrect scrobbleEpisode stopping: %sx%s - %s != %s"
                        % (
                            self.curVideoInfo["season"],
                            self.curVideoInfo["number"],
                            self.curVideoInfo["title"],
                            response["episode"]["title"],
                        )
                    )
                    self.stopScrobbler = True

                self.__scrobbleNotification(response)
                logger.debug("Scrobble response: %s" % str(response))
                return response
            else:
                logger.debug(
                    "Failed to scrobble episode: %s | %s | %s | %s"
                    % (self.traktShowSummary, self.curVideoInfo, watchedPercent, status)
                )

    def __scrobbleNotification(self, info: Dict) -> None:
        if not self.curVideoInfo:
            return

        if kodiUtilities.getSettingAsBool("scrobble_notification"):
            s = utilities.getFormattedItemName(
                self.curVideo["type"], info[self.curVideo["type"]]
            )
            kodiUtilities.notification(kodiUtilities.getString(32015), s)
