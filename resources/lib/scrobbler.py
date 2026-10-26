import logging
import math
import time
from typing import Any

import xbmc

from resources.lib import kodiUtilities, utilities
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
    curVideo: dict | None = None
    curVideoInfo: dict | None = None
    playlistIndex: int = 0
    traktShowSummary: dict | None = None
    videosToRate: list[dict]

    def __init__(self, api: Any) -> None:
        self.traktapi = api
        self.videosToRate = []

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
                    f"Current playlist item changed! Not updating time! ({self.playlistIndex:d} -> {position:d})"
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
                            logger.debug(f"Scrobble response: {response!s}")
                            self.videosToRate.append(self.curVideoInfo)
                            # update current information
                            self.curMPEpisode = epIndex
                            episode_details = kodiUtilities.getEpisodeDetailsFromKodi(
                                self.curVideo["multi_episode_data"][self.curMPEpisode],
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
                            if episode_details:
                                self.curVideoInfo = (
                                    kodiUtilities.kodiRpcToTraktMediaObject(
                                        "episode", episode_details
                                    )
                                )
                            else:
                                self.curVideoInfo = None

                            logger.debug(
                                "Multi episode transition - call start for next episode"
                            )
                            response = self.__scrobble("start")
                            self.__preFetchUserRatings(response)

                elif self.isPVR:
                    activePlayers = kodiUtilities.kodiJsonRequest(
                        {"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1}
                    )
                    logger.debug(f"Scrobble - activePlayers: {activePlayers}")
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
                        logger.debug(f"Scrobble - {result}")
                        _type, curVideo = kodiUtilities.getInfoLabelDetails(result)
                        if curVideo != self.curVideo:
                            response = self.__scrobble("stop")
                            if response is not None:
                                logger.debug(f"Scrobble response: {response!s}")
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
                                        f"Scrobble Movie type, curVideoInfo: {self.curVideoInfo}"
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
                                            self.traktShowSummary["year"] = (
                                                self.curVideo["year"]
                                            )
                                else:
                                    logger.debug(
                                        "Scrobble Couldn't set curVideoInfo/traktShowSummary for episode type"
                                    )
                                logger.debug(
                                    f"Scrobble Episode type, curVideoInfo: {self.curVideoInfo}"
                                )
                                logger.debug(
                                    f"Scrobble Episode type, traktShowSummary: {self.traktShowSummary}"
                                )
                                response = self.__scrobble("start")

                elif isSeek:
                    self.__scrobble("start")

    def playbackStarted(self, data: dict) -> None:
        logger.debug(f"playbackStarted(data: {data})")
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
            logger.debug(f"Aborting scrobble to avoid fallback: {self.curVideo}")
            return

        if "type" in self.curVideo:
            logger.debug("Watching: {}".format(self.curVideo["type"]))
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
            except Exception as e:  # noqa: BLE001 - preserve the existing broad failure boundary
                logger.debug(f"Suddenly stopped watching item: {e!s}")
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
                    movieDetailsKodi = kodiUtilities.getMovieDetailsFromKodi(
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
                    )
                    if movieDetailsKodi:
                        self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject(
                            "movie", movieDetailsKodi
                        )
                    else:
                        self.curVideoInfo = None
                elif "video_ids" in self.curVideo:
                    self.curVideoInfo = {"ids": self.curVideo["video_ids"]}
                elif "title" in self.curVideo and "year" in self.curVideo:
                    self.curVideoInfo = {
                        "title": self.curVideo["title"],
                        "year": self.curVideo["year"],
                    }
                else:
                    logger.debug("Couldn't set curVideoInfo for movie type")
                logger.debug(f"Movie type, curVideoInfo: {self.curVideoInfo}")

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
                    if episodeDetailsKodi:
                        title, year = utilities.regex_year(
                            episodeDetailsKodi["showtitle"]
                        )
                        if not year:
                            self.traktShowSummary = {
                                "title": episodeDetailsKodi["showtitle"],
                                "year": episodeDetailsKodi.get("year"),
                            }
                        else:
                            self.traktShowSummary = {"title": title, "year": year}
                        if "show_ids" in episodeDetailsKodi:
                            self.traktShowSummary["ids"] = episodeDetailsKodi[
                                "show_ids"
                            ]
                        self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject(
                            "episode", episodeDetailsKodi
                        )
                    else:
                        self.curVideoInfo = None
                    if not self.curVideoInfo:  # getEpisodeDetailsFromKodi was empty
                        logger.debug(
                            "Episode details from Kodi was empty, ID ({:d}) seems invalid, aborting further scrobbling of this episode.".format(
                                self.curVideo["id"]
                            )
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

                logger.debug(f"Episode type, curVideoInfo: {self.curVideoInfo}")
                logger.debug(f"Episode type, traktShowSummary: {self.traktShowSummary}")

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
                best_id, _ = utilities.best_id(
                    self.curVideoInfo["ids"], self.curVideo["type"]
                )
                result = {"movie": self.traktapi.getMovieSummary(best_id).to_dict()}
            elif (
                kodiUtilities.getSettingAsBool("rate_episode")
                and utilities.isEpisode(self.curVideo["type"])
                and "ids" in self.traktShowSummary
            ):
                best_id, _id_type = utilities.best_id(
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

            if result and "id" in self.curVideo:
                if utilities.isMovie(self.curVideo["type"]) and "movie" in result:
                    result["movie"]["movieid"] = self.curVideo["id"]
                elif utilities.isEpisode(self.curVideo["type"]) and "episode" in result:
                    result["episode"]["episodeid"] = self.curVideo["id"]

            self.__preFetchUserRatings(result)

    def __preFetchUserRatings(self, result: dict) -> None:
        if result:
            if (
                utilities.isMovie(self.curVideo["type"])
                and kodiUtilities.getSettingAsBool("rate_movie")
                and "movie" in result
            ):
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
            elif (
                utilities.isEpisode(self.curVideo["type"])
                and kodiUtilities.getSettingAsBool("rate_episode")
                and "episode" in result
                and "show" in result
            ):
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
            logger.debug(f"Pre-Fetch result: {result}; Info: {self.curVideoInfo}")

    def playbackResumed(self) -> None:
        if not self.isPlaying or self.isPVR:
            return

        logger.debug("playbackResumed()")
        if self.isPaused:
            p = time.time() - self.pausedAt
            logger.debug(f"Resumed after: {p!s}")
            self.pausedAt = 0
            self.isPaused = False
            self.__scrobble("start")

    def playbackPaused(self) -> None:
        if not self.isPlaying or self.isPVR:
            return

        logger.debug("playbackPaused()")
        logger.debug(f"Paused after: {self.watchedTime!s}")
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

    def __scrobble(self, status: str) -> dict | None:
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
                logger.debug(f"Scrobble response: {response!s}")
                return response
            else:
                logger.debug(
                    f"Failed to scrobble movie: {self.curVideoInfo} | {watchedPercent} | {status}"
                )

        elif utilities.isEpisode(self.curVideo["type"]) and scrobbleEpisodeOption:
            if self.isMultiPartEpisode:
                logger.debug(
                    "Multi-part episode, scrobbling part {:d} of {:d}.".format(
                        self.curMPEpisode + 1, self.curVideo["multi_episode_count"]
                    )
                )
                adjustedDuration = int(
                    self.videoDuration / self.curVideo["multi_episode_count"]
                )
                watchedPercent = (
                    (self.watchedTime - (adjustedDuration * self.curMPEpisode))
                    / adjustedDuration
                ) * 100

            logger.debug(f"scrobble sending show object: {self.traktShowSummary!s}")
            logger.debug(f"scrobble sending episode object: {self.curVideoInfo!s}")
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
                        "Searching for show title: {}".format(
                            self.traktShowSummary["title"]
                        )
                    )
                    # This text query API is basically the same as searching on the website. Works with alternative
                    # titles, unlike the scrobble function.
                    newResp = self.traktapi.getTextQuery(
                        self.traktShowSummary["title"], "show", None
                    )
                    if not newResp:
                        logger.debug("Empty Response from getTextQuery, giving up")
                    else:
                        logger.debug(f"Got Response from getTextQuery: {newResp!s}")
                        # We got something back. Have to assume the first show found is the right one; if there's more than
                        # one, there's no way to know which to use. Pull the primary title from the response (and the year,
                        # just because it's there).
                        showObj = {"title": newResp[0].title, "year": newResp[0].year}
                        logger.debug(
                            f"scrobble sending getTextQuery first show object: {showObj!s}"
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
                        "scrobble sending incorrect scrobbleEpisode stopping: {}x{} - {} != {}".format(
                            self.curVideoInfo["season"],
                            self.curVideoInfo["number"],
                            self.curVideoInfo["title"],
                            response["episode"]["title"],
                        )
                    )
                    self.stopScrobbler = True

                self.__scrobbleNotification(response)
                logger.debug(f"Scrobble response: {response!s}")
                return response
            else:
                logger.debug(
                    f"Failed to scrobble episode: {self.traktShowSummary} | {self.curVideoInfo} | {watchedPercent} | {status}"
                )

    def __scrobbleNotification(self, info: dict) -> None:
        if not self.curVideoInfo:
            return

        if kodiUtilities.getSettingAsBool("scrobble_notification"):
            s = utilities.getFormattedItemName(
                self.curVideo["type"], info[self.curVideo["type"]]
            )
            kodiUtilities.notification(kodiUtilities.getString(32015), s)
