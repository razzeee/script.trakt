# -*- coding: utf-8 -*-
#

import xbmc
import time
import logging
import utilities
import kodiUtilities
import math
from rating import ratingCheck

logger = logging.getLogger(__name__)

class Scrobbler():
    traktapi = None
    isPlaying = False
    isPaused = False
    isMultiPartEpisode = False
    lastMPCheck = 0
    curMPEpisode = 0
    videoDuration = 1
    watchedTime = 0
    pausedAt = 0
    curVideo = None
    curVideoInfo = None
    playlistLength = 1
    playlistIndex = 0
    traktShowSummary = None
    videosToRate = []

    def __init__(self, api):
        self.traktapi = api

    def _currentEpisode(self, watchedPercent, episodeCount):
        split = (100 / episodeCount)
        for i in range(episodeCount - 1, 0, -1):
            if watchedPercent >= (i * split):
                return i
        return 0

    def transitionCheck(self, isSeek=False):
        if not xbmc.Player().isPlayingVideo():
            return

        if self.isPlaying:
            t = xbmc.Player().getTime()
            l = xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition()
            if self.playlistIndex == l:
                self.watchedTime = t
            else:
                logger.debug("Current playlist item changed! Not updating time! (%d -> %d)" % (self.playlistIndex, l))

            if 'id' in self.curVideo and self.isMultiPartEpisode:
                # do transition check every minute
                if (time.time() > (self.lastMPCheck + 60)) or isSeek:
                    self.lastMPCheck = time.time()
                    watchedPercent = self.__calculateWatchedPercent()
                    epIndex = self._currentEpisode(watchedPercent, self.curVideo['multi_episode_count'])
                    if self.curMPEpisode != epIndex:
                        response = self.__scrobble('stop')
                        if response is not None:
                            logger.debug("Scrobble response: %s" % str(response))
                            self.videosToRate.append(self.curVideoInfo)
                            # update current information
                            self.curMPEpisode = epIndex
                            self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject('episode', kodiUtilities.getEpisodeDetailsFromKodi(self.curVideo['multi_episode_data'][self.curMPEpisode], ['showtitle', 'season', 'episode', 'tvshowid', 'uniqueid', 'file', 'playcount']))

                            logger.debug("Multi episode transition - call start for next episode")
                            response = self.__scrobble('start')
                            self.__preFetchUserRatings(response)
            elif isSeek:
                self.__scrobble('start')

    def playbackStarted(self, data):
        logger.debug("playbackStarted(data: %s)" % data)
        if not data:
            return
        self.curVideo = data
        self.curVideoInfo = None
        self.videosToRate = []

        if not kodiUtilities.getSettingAsBool('scrobble_fallback') and 'id' not in self.curVideo and 'video_ids' not in self.curVideo:
            logger.debug('Aborting scrobble to avoid fallback: %s' % (self.curVideo))
            return
             
        if 'type' in self.curVideo:
            logger.debug("Watching: %s" % self.curVideo['type'])
            if not xbmc.Player().isPlayingVideo():
                logger.debug("Suddenly stopped watching item")
                return
            xbmc.sleep(1000)  # Wait for possible silent seek (caused by resuming)
            try:
                self.watchedTime = xbmc.Player().getTime()
                self.videoDuration = xbmc.Player().getTotalTime()
            except Exception as e:
                logger.debug("Suddenly stopped watching item: %s" % e.message)
                self.curVideo = None
                return

            if self.videoDuration == 0:
                if utilities.isMovie(self.curVideo['type']):
                    self.videoDuration = 90
                elif utilities.isEpisode(self.curVideo['type']):
                    self.videoDuration = 30
                else:
                    self.videoDuration = 1

            self.playlistLength = len(xbmc.PlayList(xbmc.PLAYLIST_VIDEO))
            self.playlistIndex = xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition()
            if self.playlistLength == 0:
                logger.debug("Warning: Cant find playlist length, assuming that this item is by itself")
                self.playlistLength = 1

            self.isMultiPartEpisode = False
            if utilities.isMovie(self.curVideo['type']):
                if 'id' in self.curVideo:
                    self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject('movie', kodiUtilities.getMovieDetailsFromKodi(self.curVideo['id'], ['imdbnumber', 'title', 'year', 'file', 'lastplayed', 'playcount']))
                elif 'video_ids' in self.curVideo:
                    self.curVideoInfo = {'ids': self.curVideo['video_ids']}
                elif 'title' in self.curVideo and 'year' in self.curVideo:
                    self.curVideoInfo = {'title': self.curVideo['title'], 'year': self.curVideo['year']}

            elif utilities.isEpisode(self.curVideo['type']):
                if 'id' in self.curVideo:
                    episodeDetailsKodi = kodiUtilities.getEpisodeDetailsFromKodi(self.curVideo['id'], ['showtitle', 'season', 'episode', 'tvshowid', 'uniqueid', 'file', 'playcount'])
                    tvdb = episodeDetailsKodi['imdbnumber']
                    title, year = utilities.regex_year(episodeDetailsKodi['showtitle'])
                    if not year:
                        self.traktShowSummary = {'title': episodeDetailsKodi['showtitle'], 'year': episodeDetailsKodi['year']}
                    else:
                        self.traktShowSummary = {'title': title, 'year': year}
                    if tvdb:
                        self.traktShowSummary['ids'] = {'tvdb': tvdb}
                    self.curVideoInfo = kodiUtilities.kodiRpcToTraktMediaObject('episode', episodeDetailsKodi)
                    if not self.curVideoInfo:  # getEpisodeDetailsFromKodi was empty
                        logger.debug("Episode details from Kodi was empty, ID (%d) seems invalid, aborting further scrobbling of this episode." % self.curVideo['id'])
                        self.curVideo = None
                        self.isPlaying = False
                        self.watchedTime = 0
                        return
                elif 'video_ids' in self.curVideo and 'season' in self.curVideo and 'episode' in self.curVideo:
                    self.curVideoInfo = {'season': self.curVideo['season'], 'number': self.curVideo['episode']}
                    self.traktShowSummary = {'ids': self.curVideo['video_ids']}
                elif 'title' in self.curVideo and 'season' in self.curVideo and 'episode' in self.curVideo:
                    self.curVideoInfo = {'title': self.curVideo['title'], 'season': self.curVideo['season'],
                                         'number': self.curVideo['episode']}

                    title, year = utilities.regex_year(self.curVideo['showtitle'])
                    if not year:
                        self.traktShowSummary = {'title': self.curVideo['showtitle']}
                    else:
                        self.traktShowSummary = {'title': title, 'year': year}

                    if 'year' in self.curVideo:
                        self.traktShowSummary['year'] = self.curVideo['year']

                if 'multi_episode_count' in self.curVideo and self.curVideo['multi_episode_count'] > 1:
                    self.isMultiPartEpisode = True

            self.isPlaying = True
            self.isPaused = False

            result = {}
            if kodiUtilities.getSettingAsBool('scrobble_movie') or kodiUtilities.getSettingAsBool('scrobble_episode'):
                result = self.__scrobble('start')
            elif kodiUtilities.getSettingAsBool('rate_movie') and utilities.isMovie(self.curVideo['type']) and 'ids' in self.curVideoInfo:
                best_id = utilities.best_id(self.curVideoInfo['ids'])
                result = {'movie': self.traktapi.getMovieSummary(best_id).to_dict()}
            elif kodiUtilities.getSettingAsBool('rate_episode') and utilities.isEpisode(self.curVideo['type']) and 'ids' in self.traktShowSummary:
                best_id = utilities.best_id(self.traktShowSummary['ids'])
                result = {'show': self.traktapi.getShowSummary(best_id).to_dict(),
                          'episode': self.traktapi.getEpisodeSummary(best_id, self.curVideoInfo['season'],
                                                                     self.curVideoInfo['number']).to_dict()}
                result['episode']['season'] = self.curVideoInfo['season']

            if 'id' in self.curVideo:
                if utilities.isMovie(self.curVideo['type']):
                    result['movie']['movieid'] = self.curVideo['id']
                elif utilities.isEpisode(self.curVideo['type']):
                    result['episode']['episodeid'] = self.curVideo['id']
                
            self.__preFetchUserRatings(result)

    def __preFetchUserRatings(self, result):
        if result:
            if utilities.isMovie(self.curVideo['type']) and kodiUtilities.getSettingAsBool('rate_movie'):
                # pre-get summary information, for faster rating dialog.
                logger.debug("Movie rating is enabled, pre-fetching summary information.")
                self.curVideoInfo = result['movie']
                self.curVideoInfo['user'] = {'ratings': self.traktapi.getMovieRatingForUser(result['movie']['ids']['trakt'], 'trakt')}
            elif utilities.isEpisode(self.curVideo['type']) and kodiUtilities.getSettingAsBool('rate_episode'):
                # pre-get summary information, for faster rating dialog.
                logger.debug("Episode rating is enabled, pre-fetching summary information.")
                self.curVideoInfo = result['episode']
                self.curVideoInfo['user'] = {'ratings': self.traktapi.getEpisodeRatingForUser(result['show']['ids']['trakt'],
                                                                                              self.curVideoInfo['season'], self.curVideoInfo['number'], 'trakt')}
            logger.debug('Pre-Fetch result: %s; Info: %s' % (result, self.curVideoInfo))

    def playbackResumed(self):
        if not self.isPlaying:
            return

        logger.debug("playbackResumed()")
        if self.isPaused:
            p = time.time() - self.pausedAt
            logger.debug("Resumed after: %s" % str(p))
            self.pausedAt = 0
            self.isPaused = False
            self.__scrobble('start')

    def playbackPaused(self):
        if not self.isPlaying:
            return

        logger.debug("playbackPaused()")
        logger.debug("Paused after: %s" % str(self.watchedTime))
        self.isPaused = True
        self.pausedAt = time.time()
        self.__scrobble('pause')

    def playbackSeek(self):
        if not self.isPlaying:
            return

        logger.debug("playbackSeek()")
        self.transitionCheck(isSeek=True)

    def playbackEnded(self):
        self.videosToRate.append(self.curVideoInfo)
        if not self.isPlaying:
            return

        logger.debug("playbackEnded()")
        if not self.videosToRate:
            logger.debug("Warning: Playback ended but video forgotten.")
            return
        self.isPlaying = False
        if self.watchedTime != 0:
            if 'type' in self.curVideo:
                self.__scrobble('stop')
                ratingCheck(self.curVideo['type'], self.videosToRate, self.watchedTime, self.videoDuration, self.playlistLength)
            self.watchedTime = 0
            self.isMultiPartEpisode = False
        self.videosToRate = []
        self.curVideoInfo = None
        self.curVideo = None
        self.playlistLength = 0
        self.playlistIndex = 0

    def __calculateWatchedPercent(self):
        return (self.watchedTime / math.floor(self.videoDuration)) * 100  # we need to floor this, so this calculation yields the same result as the playback progress calculation

    def __scrobble(self, status):
        if not self.curVideoInfo:
            return

        logger.debug("scrobble()")
        scrobbleMovieOption = kodiUtilities.getSettingAsBool('scrobble_movie')
        scrobbleEpisodeOption = kodiUtilities.getSettingAsBool('scrobble_episode')

        watchedPercent = self.__calculateWatchedPercent()

        if utilities.isMovie(self.curVideo['type']) and scrobbleMovieOption:
            response = self.traktapi.scrobbleMovie(self.curVideoInfo, watchedPercent, status)
            if response is not None:
                self.__scrobbleNotification(response)
                logger.debug("Scrobble response: %s" % str(response))
                return response
            else:
                logger.debug("Failed to scrobble movie: %s | %s | %s" % (self.curVideoInfo, watchedPercent, status))

        elif utilities.isEpisode(self.curVideo['type']) and scrobbleEpisodeOption:
            if self.isMultiPartEpisode:
                logger.debug("Multi-part episode, scrobbling part %d of %d." % (self.curMPEpisode + 1, self.curVideo['multi_episode_count']))
                adjustedDuration = int(self.videoDuration / self.curVideo['multi_episode_count'])
                watchedPercent = ((self.watchedTime - (adjustedDuration * self.curMPEpisode)) / adjustedDuration) * 100

            response = self.traktapi.scrobbleEpisode(self.traktShowSummary, self.curVideoInfo, watchedPercent, status)
            if response is not None:
                self.__scrobbleNotification(response)
                logger.debug("Scrobble response: %s" % str(response))
                return response
            else:
                logger.debug("Failed to scrobble episode: %s | %s | %s | %s" % (self.traktShowSummary,
                                                                                self.curVideoInfo, watchedPercent,
                                                                                status))

    def __scrobbleNotification(self, info):
        if not self.curVideoInfo:
            return

        if kodiUtilities.getSettingAsBool("scrobble_notification"):
            s = kodiUtilities.getFormattedItemName(self.curVideo['type'], info[self.curVideo['type']])
            kodiUtilities.notification(kodiUtilities.getString(32015), s)
