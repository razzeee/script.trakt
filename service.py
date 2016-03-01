# -*- coding: utf-8 -*-
import threading
import logging
import xbmc

from traktapi import traktAPI

import globals
from rating import rateMedia
from scrobbler import Scrobbler
import sqlitequeue
from sync import Sync
import utilities
import time
import gui_utils
import xbmcgui
import json

logger = logging.getLogger(__name__)

class traktService:
    scrobbler = None
    updateTagsThread = None
    syncThread = None
    dispatchQueue = sqlitequeue.SqliteQueue()

    def __init__(self):
        threading.Thread.name = 'trakt'

    def _dispatchQueue(self, data):
        logger.debug("Queuing for dispatch: %s" % data)
        self.dispatchQueue.append(data)

    def _dispatch(self, data):
        try:
            logger.debug("Dispatch: %s" % data)
            action = data['action']
            if action == 'started':
                del data['action']
                self.scrobbler.playbackStarted(data)
            elif action == 'ended' or action == 'stopped':
                self.scrobbler.playbackEnded()
            elif action == 'paused':
                self.scrobbler.playbackPaused()
            elif action == 'resumed':
                self.scrobbler.playbackResumed()
            elif action == 'seek' or action == 'seekchapter':
                self.scrobbler.playbackSeek()
            elif action == 'scanFinished':
                if utilities.getSettingAsBool('sync_on_update'):
                    logger.debug("Performing sync after library update.")
                    self.doSync()
            elif action == 'databaseCleaned':
                if utilities.getSettingAsBool('sync_on_update') and (utilities.getSettingAsBool('clean_trakt_movies') or utilities.getSettingAsBool('clean_trakt_episodes')):
                    logger.debug("Performing sync after library clean.")
                    self.doSync()
            elif action == 'settingsChanged':
                logger.debug("Settings changed, reloading.")
                globals.traktapi.updateSettings()
            elif action == 'markWatched':
                del data['action']
                self.doMarkWatched(data)
            elif action == 'manualRating':
                ratingData = data['ratingData']
                self.doManualRating(ratingData)
            elif action == 'addtowatchlist':  # add to watchlist
                del data['action']
                self.doAddToWatchlist(data)
            elif action == 'manualSync':
                if not self.syncThread.isAlive():
                    logger.debug("Performing a manual sync.")
                    self.doSync(manual=True, silent=data['silent'], library=data['library'])
                else:
                    logger.debug("There already is a sync in progress.")
            elif action == 'settings':
                utilities.showSettings()
            else:
                logger.debug("Unknown dispatch action, '%s'." % action)
        except Exception as ex:
            message = utilities.createError(ex)
            logger.fatal(message)

    def run(self):
        startup_delay = utilities.getSettingAsInt('startup_delay')
        if startup_delay:
            logger.debug("Delaying startup by %d seconds." % startup_delay)
            xbmc.sleep(startup_delay * 1000)

        logger.debug("Service thread starting.")

        # purge queue before doing anything
        self.dispatchQueue.purge()

        # setup event driven classes
        self.Player = traktPlayer(action=self._dispatchQueue)
        self.Monitor = traktMonitor(action=self._dispatchQueue)

        # init traktapi class
        globals.traktapi = traktAPI()

        # init sync thread
        self.syncThread = syncThread()

        # init scrobbler class
        self.scrobbler = Scrobbler(globals.traktapi)

        # start loop for events
        while not self.Monitor.abortRequested():
            if not utilities.getSetting('authorization'):
                last_reminder = utilities.getSettingAsInt('last_reminder')
                now = int(time.time())
                if last_reminder >= 0 and last_reminder < now - (24 * 60 * 60):
                    gui_utils.get_pin()
                
            while len(self.dispatchQueue) and (not self.Monitor.abortRequested()):
                data = self.dispatchQueue.get()
                logger.debug("Queued dispatch: %s" % data)
                self._dispatch(data)

            if xbmc.Player().isPlayingVideo():
                self.scrobbler.transitionCheck()

            if self.Monitor.waitForAbort(1):
                # Abort was requested while waiting. We should exit
                break

        # we are shutting down
        logger.debug("Beginning shut down.")

        # delete player/monitor
        del self.Player
        del self.Monitor

        # check if sync thread is running, if so, join it.
        if self.syncThread.isAlive():
            self.syncThread.join()

    def doManualRating(self, data):
        action = data['action']
        media_type = data['media_type']
        summaryInfo = None

        if not utilities.isValidMediaType(media_type):
            logger.debug("doManualRating(): Invalid media type '%s' passed for manual %s." % (media_type, action))
            return

        if not data['action'] in ['rate', 'unrate']:
            logger.debug("doManualRating(): Unknown action passed.")
            return

        logger.debug("Getting data for manual %s of %s: video_id: |%s| dbid: |%s|" % (action, media_type, data.get('video_id'), data.get('dbid')))

        id_type = utilities.parseIdToTraktIds(str(data['video_id']), media_type)[1]

        if not id_type:
            logger.debug("doManualRating(): Unrecognized id_type: |%s|-|%s|." % (media_type, data['video_id']))
            return
            
        ids = globals.traktapi.getIdLookup(data['video_id'], id_type)
        
        if not ids:
            logger.debug("doManualRating(): No Results for: |%s|-|%s|." % (media_type, data['video_id']))
            return
            
        trakt_id = dict(ids[0].keys)['trakt']
        if utilities.isEpisode(media_type):
            summaryInfo = globals.traktapi.getEpisodeSummary(trakt_id, data['season'], data['episode'])
            userInfo = globals.traktapi.getEpisodeRatingForUser(trakt_id, data['season'], data['episode'], 'trakt')
        elif utilities.isSeason(media_type):
            summaryInfo = globals.traktapi.getShowSummary(trakt_id)
            userInfo = globals.traktapi.getSeasonRatingForUser(trakt_id, data['season'], 'trakt')
        elif utilities.isShow(media_type):
            summaryInfo = globals.traktapi.getShowSummary(trakt_id)
            userInfo = globals.traktapi.getShowRatingForUser(trakt_id, 'trakt')
        elif utilities.isMovie(media_type):
            summaryInfo = globals.traktapi.getMovieSummary(trakt_id)
            userInfo = globals.traktapi.getMovieRatingForUser(trakt_id, 'trakt')

        if summaryInfo is not None:
            summaryInfo = summaryInfo.to_dict()
            summaryInfo['user'] = {'ratings': userInfo}
            if utilities.isEpisode(media_type):
                summaryInfo['season'] = data['season']
                summaryInfo['number'] = data['episode']
                summaryInfo['episodeid'] = data.get('dbid')
            elif utilities.isSeason(media_type):
                summaryInfo['season'] = data['season']
            elif utilities.isMovie(media_type):
                summaryInfo['movieid'] = data.get('dbid')
            elif utilities.isShow(media_type):
                summaryInfo['tvshowid'] = data.get('dbid')

            if action == 'rate':
                if not 'rating' in data:
                    rateMedia(media_type, [summaryInfo])
                else:
                    rateMedia(media_type, [summaryInfo], rating=data['rating'])
        else:
            logger.debug("doManualRating(): Summary info was empty, possible problem retrieving data from Trakt.tv")

    def doAddToWatchlist(self, data):
        media_type = data['media_type']

        if utilities.isMovie(media_type):
            summaryInfo = globals.traktapi.getMovieSummary(data['id']).to_dict()
            if summaryInfo:
                s = utilities.getFormattedItemName(media_type, summaryInfo)
                logger.debug("doAddToWatchlist(): '%s' trying to add to users watchlist." % s)
                params = {'movies': [summaryInfo]}
                logger.debug("doAddToWatchlist(): %s" % str(params))

                result = globals.traktapi.addToWatchlist(params)
                if result:
                    utilities.notification(utilities.getString(32165), s)
                else:
                    utilities.notification(utilities.getString(32166), s)
        elif utilities.isEpisode(media_type):
            summaryInfo = {'shows': [{'ids': utilities.parseIdToTraktIds(data['id'], media_type)[0],
                                      'seasons': [{'number': data['season'], 'episodes': [{'number':data['number']}]}]}]}
            logger.debug("doAddToWatchlist(): %s" % str(summaryInfo))
            s = utilities.getFormattedItemName(media_type, data)

            result = globals.traktapi.addToWatchlist(summaryInfo)
            if result:
                utilities.notification(utilities.getString(32165), s)
            else:
                utilities.notification(utilities.getString(32166), s)
        elif utilities.isSeason(media_type):
            summaryInfo = {'shows': [{'ids': utilities.parseIdToTraktIds(data['id'], media_type)[0],
                                      'seasons': [{'number': data['season']}]}]}
            s = utilities.getFormattedItemName(media_type, data)

            logger.debug("doAddToWatchlist(): '%s - Season %d' trying to add to users watchlist."
                         % (data['id'], data['season']))

            result = globals.traktapi.addToWatchlist(summaryInfo)
            if result:
                utilities.notification(utilities.getString(32165), s)
            else:
                utilities.notification(utilities.getString(32166), s)
        elif utilities.isShow(media_type):
            summaryInfo = {'shows': [{'ids': utilities.parseIdToTraktIds(data['id'], media_type)[0]}]}
            s = utilities.getFormattedItemName(media_type, data)
            logger.debug("doAddToWatchlist(): %s" % str(summaryInfo))

            result = globals.traktapi.addToWatchlist(summaryInfo)
            if result:
                utilities.notification(utilities.getString(32165), s)
            else:
                utilities.notification(utilities.getString(32166), s)

    def doMarkWatched(self, data):

        media_type = data['media_type']

        if utilities.isMovie(media_type):
            summaryInfo = globals.traktapi.getMovieSummary(data['id']).to_dict()
            if summaryInfo:
                if not summaryInfo['watched']:
                    s = utilities.getFormattedItemName(media_type, summaryInfo)
                    logger.debug("doMarkWatched(): '%s' is not watched on Trakt, marking it as watched." % s)
                    params = {'movies': [summaryInfo]}
                    logger.debug("doMarkWatched(): %s" % str(params))

                    result = globals.traktapi.addToHistory(params)
                    if result:
                        utilities.notification(utilities.getString(32113), s)
                    else:
                        utilities.notification(utilities.getString(32114), s)
        elif utilities.isEpisode(media_type):
            summaryInfo = {'shows': [{'ids':utilities.parseIdToTraktIds(data['id'],media_type)[0], 'seasons': [{'number': data['season'], 'episodes': [{'number':data['number']}]}]}]}
            logger.debug("doMarkWatched(): %s" % str(summaryInfo))
            s = utilities.getFormattedItemName(media_type, data)

            result = globals.traktapi.addToHistory(summaryInfo)
            if result:
                utilities.notification(utilities.getString(32113), s)
            else:
                utilities.notification(utilities.getString(32114), s)
        elif utilities.isSeason(media_type):
            summaryInfo = {'shows': [{'ids':utilities.parseIdToTraktIds(data['id'],media_type)[0], 'seasons': [{'number': data['season'], 'episodes': []}]}]}
            s = utilities.getFormattedItemName(media_type, data)
            for ep in data['episodes']:
                summaryInfo['shows'][0]['seasons'][0]['episodes'].append({'number': ep})

            logger.debug("doMarkWatched(): '%s - Season %d' has %d episode(s) that are going to be marked as watched." % (data['id'], data['season'], len(summaryInfo['shows'][0]['seasons'][0]['episodes'])))

            if len(summaryInfo['shows'][0]['seasons'][0]['episodes']) > 0:
                logger.debug("doMarkWatched(): %s" % str(summaryInfo))

                result = globals.traktapi.addToHistory(summaryInfo)
                if result:
                    utilities.notification(utilities.getString(32113), utilities.getString(32115) % (result['added']['episodes'], s))
                else:
                    utilities.notification(utilities.getString(32114), s)
        elif utilities.isShow(media_type):
            summaryInfo = {'shows': [{'ids':utilities.parseIdToTraktIds(data['id'],media_type)[0], 'seasons': []}]}
            if summaryInfo:
                s = utilities.getFormattedItemName(media_type, data)
                logger.debug('data: %s' % data)
                for season in data['seasons']:
                    episodeJson = []
                    for episode in data['seasons'][season]:
                        episodeJson.append({'number': episode})
                    summaryInfo['shows'][0]['seasons'].append({'number': season, 'episodes': episodeJson})

                if len(summaryInfo['shows'][0]['seasons'][0]['episodes']) > 0:
                    logger.debug("doMarkWatched(): %s" % str(summaryInfo))

                    result = globals.traktapi.addToHistory(summaryInfo)
                    if result:
                        utilities.notification(utilities.getString(32113), utilities.getString(32115) % (result['added']['episodes'], s))
                    else:
                        utilities.notification(utilities.getString(32114), s)

    def doSync(self, manual=False, silent=False, library="all"):
        self.syncThread = syncThread(manual, silent, library)
        self.syncThread.start()

class syncThread(threading.Thread):

    _isManual = False

    def __init__(self, isManual=False, runSilent=False, library="all"):
        threading.Thread.__init__(self)
        self.name = "trakt-sync"
        self._isManual = isManual
        self._runSilent = runSilent
        self._library = library

    def run(self):
        sync = Sync(show_progress=self._isManual, run_silent=self._runSilent, library=self._library, api=globals.traktapi)
        sync.sync()


class traktMonitor(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        self.action = kwargs['action']
        # xbmc.getCondVisibility('Library.IsScanningVideo') returns false when cleaning during update...
        self.scanning_video = False
        logger.debug("[traktMonitor] Initalized.")

    # called when database gets updated and return video or music to indicate which DB has been changed
    def onScanFinished(self, database):
        if database == 'video':
            self.scanning_video = False
            logger.debug("[traktMonitor] onScanFinished(database: %s)" % database)
            data = {'action': 'scanFinished'}
            self.action(data)

    # called when database update starts and return video or music to indicate which DB is being updated
    def onDatabaseScanStarted(self, database):
        if database == "video":
            self.scanning_video = True
            logger.debug("[traktMonitor] onDatabaseScanStarted(database: %s)" % database)

    def onSettingsChanged(self):
        data = {'action': 'settingsChanged'}
        self.action(data)

    def onCleanFinished(self, database):
        if database == "video" and not self.scanning_video:  # Ignore clean on update.
            data = {'action': 'databaseCleaned'}
            self.action(data)

class traktPlayer(xbmc.Player):

    _playing = False
    plIndex = None

    def __init__(self, *args, **kwargs):
        self.action = kwargs['action']
        logger.debug("[traktPlayer] Initalized.")

    # called when kodi starts playing a file
    def onPlayBackStarted(self):
        xbmc.sleep(1000)
        self.type = None
        self.id = None

        # take the user start scrobble offset into account
        scrobbleStartOffset = utilities.getSettingAsInt('scrobble_start_offset')*60
        if scrobbleStartOffset > 0:
            waitFor = 10
            waitedFor = 0
            # check each 10 seconds if we can abort or proceed
            while not xbmc.abortRequested and scrobbleStartOffset > waitedFor:
                waitedFor += waitFor
                time.sleep(waitFor)
                if not self.isPlayingVideo():
                    logger.debug('[traktPlayer] Playback stopped before reaching the scrobble offset')
                    return

        # only do anything if we're playing a video
        if self.isPlayingVideo():
            # get item data from json rpc
            result = utilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'Player.GetItem', 'params': {'playerid': 1}, 'id': 1})
            if result:
                logger.debug("[traktPlayer] onPlayBackStarted() - %s" % result)
                # check for exclusion
                _filename = None
                try:
                    _filename = self.getPlayingFile()
                except:
                    logger.debug("[traktPlayer] onPlayBackStarted() - Exception trying to get playing filename, player suddenly stopped.")
                    return
    
                if utilities.checkExclusion(_filename):
                    logger.debug("[traktPlayer] onPlayBackStarted() - '%s' is in exclusion settings, ignoring." % _filename)
                    return
    
                self.type = result['item']['type']
    
                data = {'action': 'started'}
    
                # check type of item
                if 'id' not in result['item']:
                    # do a deeper check to see if we have enough data to perform scrobbles
                    logger.debug("[traktPlayer] onPlayBackStarted() - Started playing a non-library file, checking available data.")
    
                    season = xbmc.getInfoLabel('VideoPlayer.Season')
                    episode = xbmc.getInfoLabel('VideoPlayer.Episode')
                    showtitle = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
                    year = xbmc.getInfoLabel('VideoPlayer.Year')
                    video_ids = xbmcgui.Window(10000).getProperty('script.trakt.ids')
                    if video_ids:
                        data['video_ids'] = json.loads(video_ids)
    
                    logger.debug("[traktPlayer] info - ids: %s, showtitle: %s, Year: %s, Season: %s, Episode: %s" % (video_ids, showtitle, year, season, episode))
    
                    if season and episode and (showtitle or video_ids):
                        # we have season, episode and either a show title or video_ids, can scrobble this as an episode
                        self.type = 'episode'
                        data['type'] = 'episode'
                        data['season'] = int(season)
                        data['episode'] = int(episode)
                        data['showtitle'] = showtitle
                        data['title'] = xbmc.getInfoLabel('VideoPlayer.Title')
                        if year.isdigit():
                            data['year'] = int(year)
                        logger.debug("[traktPlayer] onPlayBackStarted() - Playing a non-library 'episode' - %s - S%02dE%02d - %s." % (data['showtitle'], data['season'], data['episode'], data['title']))
                    elif (year or video_ids) and not season and not showtitle:
                        # we have a year or video_id and no season/showtitle info, enough for a movie
                        self.type = 'movie'
                        data['type'] = 'movie'
                        if year.isdigit():
                            data['year'] = int(year)
                        data['title'] = xbmc.getInfoLabel('VideoPlayer.Title')
                        logger.debug("[traktPlayer] onPlayBackStarted() - Playing a non-library 'movie' - %s (%s)." % (data['title'], data.get('year', 'NaN')))
                    elif showtitle:
                        title, season, episode = utilities.regex_tvshow(False, showtitle)
                        data['type'] = 'episode'
                        data['season'] = season
                        data['episode'] = episode
                        data['title'] = data['showtitle'] = title
                        logger.debug("[traktPlayer] onPlayBackStarted() - Title: %s, showtitle: %s, season: %d, episode: %d" % (title, showtitle, season, episode))
                    else:
                        logger.debug("[traktPlayer] onPlayBackStarted() - Non-library file, not enough data for scrobbling, skipping.")
                        return
    
                elif self.type == 'episode' or self.type == 'movie':
                    # get library id
                    self.id = result['item']['id']
                    data['id'] = self.id
                    data['type'] = self.type
    
                    if self.type == 'episode':
                        logger.debug("[traktPlayer] onPlayBackStarted() - Doing multi-part episode check.")
                        result = utilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodeDetails', 'params': {'episodeid': self.id, 'properties': ['tvshowid', 'season', 'episode', 'file']}, 'id': 1})
                        if result:
                            logger.debug("[traktPlayer] onPlayBackStarted() - %s" % result)
                            tvshowid = int(result['episodedetails']['tvshowid'])
                            season = int(result['episodedetails']['season'])
                            currentfile = result['episodedetails']['file']
    
                            result = utilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': tvshowid, 'season': season, 'properties': ['episode', 'file'], 'sort': {'method': 'episode'}}, 'id': 1})
                            if result:
                                logger.debug("[traktPlayer] onPlayBackStarted() - %s" % result)
                                # make sure episodes array exists in results
                                if 'episodes' in result:
                                    multi = []
                                    for i in range(result['limits']['start'], result['limits']['total']):
                                        if currentfile == result['episodes'][i]['file']:
                                            multi.append(result['episodes'][i]['episodeid'])
                                    if len(multi) > 1:
                                        data['multi_episode_data'] = multi
                                        data['multi_episode_count'] = len(multi)
                                        logger.debug("[traktPlayer] onPlayBackStarted() - This episode is part of a multi-part episode.")
                                    else:
                                        logger.debug("[traktPlayer] onPlayBackStarted() - This is a single episode.")
    
                else:
                    logger.debug("[traktPlayer] onPlayBackStarted() - Video type '%s' unrecognized, skipping." % self.type)
                    return
    
                pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                plSize = len(pl)
                if plSize > 1:
                    pos = pl.getposition()
                    if not self.plIndex is None:
                        logger.debug("[traktPlayer] onPlayBackStarted() - User manually skipped to next (or previous) video, forcing playback ended event.")
                        self.onPlayBackEnded()
                    self.plIndex = pos
                    logger.debug("[traktPlayer] onPlayBackStarted() - Playlist contains %d item(s), and is currently on item %d" % (plSize, (pos + 1)))
    
                self._playing = True
    
                # send dispatch
                self.action(data)

    # called when kodi stops playing a file
    def onPlayBackEnded(self):
        xbmcgui.Window(10000).clearProperty('script.trakt.ids')
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackEnded() - %s" % self.isPlayingVideo())
            self._playing = False
            self.plIndex = None
            data = {'action': 'ended'}
            self.action(data)

    # called when user stops kodi playing a file
    def onPlayBackStopped(self):
        xbmcgui.Window(10000).clearProperty('script.trakt.ids')
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackStopped() - %s" % self.isPlayingVideo())
            self._playing = False
            self.plIndex = None
            data = {'action': 'stopped'}
            self.action(data)

    # called when user pauses a playing file
    def onPlayBackPaused(self):
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackPaused() - %s" % self.isPlayingVideo())
            data = {'action': 'paused'}
            self.action(data)

    # called when user resumes a paused file
    def onPlayBackResumed(self):
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackResumed() - %s" % self.isPlayingVideo())
            data = {'action': 'resumed'}
            self.action(data)

    # called when user queues the next item
    def onQueueNextItem(self):
        if self._playing:
            logger.debug("[traktPlayer] onQueueNextItem() - %s" % self.isPlayingVideo())

    # called when players speed changes. (eg. user FF/RW)
    def onPlayBackSpeedChanged(self, speed):
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackSpeedChanged(speed: %s) - %s" % (str(speed), self.isPlayingVideo()))

    # called when user seeks to a time
    def onPlayBackSeek(self, time, offset):
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackSeek(time: %s, offset: %s) - %s" % (str(time), str(offset), self.isPlayingVideo()))
            data = {'action': 'seek', 'time': time, 'offset': offset}
            self.action(data)

    # called when user performs a chapter seek
    def onPlayBackSeekChapter(self, chapter):
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackSeekChapter(chapter: %s) - %s" % (str(chapter), self.isPlayingVideo()))
            data = {'action': 'seekchapter', 'chapter': chapter}
            self.action(data)
