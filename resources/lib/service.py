# -*- coding: utf-8 -*-
import threading
import logging
import xbmc
import time
import xbmcgui
import json
import re
import urllib

from resources.lib import globals
from resources.lib import sqlitequeue
from resources.lib import utilities
from resources.lib import kodiUtilities
from resources.lib.rating import rateMedia
from resources.lib.scrobbler import Scrobbler
from resources.lib.sync import Sync
from resources.lib.traktapi import traktAPI

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
                if kodiUtilities.getSettingAsBool('sync_on_update'):
                    logger.debug("Performing sync after library update.")
                    self.doSync()
            elif action == 'databaseCleaned':
                if kodiUtilities.getSettingAsBool('sync_on_update') and (kodiUtilities.getSettingAsBool('clean_trakt_movies') or kodiUtilities.getSettingAsBool('clean_trakt_episodes')):
                    logger.debug("Performing sync after library clean.")
                    self.doSync()
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
                kodiUtilities.showSettings()
            elif action == 'auth_info':
                xbmc.executebuiltin('Dialog.Close(all, true)')
                # init traktapi class
                globals.traktapi = traktAPI(True)
            else:
                logger.debug("Unknown dispatch action, '%s'." % action)
        except Exception as ex:
            message = utilities.createError(ex)
            logger.fatal(message)

    def run(self):
        startup_delay = kodiUtilities.getSettingAsInt('startup_delay')
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

        if 'video_ids' in data:
            logger.debug("Getting data for manual %s of %s: video_ids: |%s| dbid: |%s|" % (
                action, media_type, data.get('video_ids'), data.get('dbid')))

            temp_ids, id_type = utilities.parseIdToTraktIds(
                str(utilities.best_id(data['video_ids'], media_type)), media_type)

        else:
            logger.debug("Getting data for manual %s of %s: video_id: |%s| dbid: |%s|" % (
                action, media_type, data.get('video_id'), data.get('dbid')))

            temp_ids, id_type = utilities.parseIdToTraktIds(
                str(data['video_id']), media_type)

        best_id = temp_ids[id_type]

        if not id_type:
            logger.debug("doManualRating(): Unrecognized id_type: |%s|-|%s|." %
                         (media_type, best_id))
            return

        ids = globals.traktapi.getIdLookup(best_id, id_type)

        if not ids:
            logger.debug("doManualRating(): No Results for: |%s|-|%s|." %
                         (media_type, best_id))
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
            elif action == 'unrate':
                rateMedia(media_type, [summaryInfo], unrate=True)
        else:
            logger.debug("doManualRating(): Summary info was empty, possible problem retrieving data from Trakt.tv")

    def doAddToWatchlist(self, data):
        media_type = data['media_type']

        if utilities.isMovie(media_type):
            temp_ids, id_type = utilities.parseIdToTraktIds(
                str(utilities.best_id(data['ids'], media_type)), media_type)

            best_id = temp_ids[id_type]

            summaryInfo = globals.traktapi.getMovieSummary(
                best_id).to_dict()
            if summaryInfo:
                s = utilities.getFormattedItemName(media_type, summaryInfo)
                logger.debug("doAddToWatchlist(): '%s' trying to add to users watchlist." % s)
                params = {'movies': [summaryInfo]}
                logger.debug("doAddToWatchlist(): %s" % str(params))

                result = globals.traktapi.addToWatchlist(params)
                if result:
                    kodiUtilities.notification(kodiUtilities.getString(32165), s)
                else:
                    kodiUtilities.notification(kodiUtilities.getString(32166), s)
        elif utilities.isEpisode(media_type):
            summaryInfo = {'shows': [{'ids': data['ids'],
                                      'seasons': [{'number': data['season'], 'episodes': [{'number': data['number']}]}]}]}
            logger.debug("doAddToWatchlist(): %s" % str(summaryInfo))
            s = utilities.getFormattedItemName(media_type, data)

            result = globals.traktapi.addToWatchlist(summaryInfo)
            if result:
                kodiUtilities.notification(kodiUtilities.getString(32165), s)
            else:
                kodiUtilities.notification(kodiUtilities.getString(32166), s)
        elif utilities.isSeason(media_type):
            summaryInfo = {'shows': [{'ids': data['ids'],
                                      'seasons': [{'number': data['season']}]}]}
            s = utilities.getFormattedItemName(media_type, data)

            logger.debug("doAddToWatchlist(): '%s - Season %d' trying to add to users watchlist."
                         % (ids, data['season']))

            result = globals.traktapi.addToWatchlist(summaryInfo)
            if result:
                kodiUtilities.notification(kodiUtilities.getString(32165), s)
            else:
                kodiUtilities.notification(kodiUtilities.getString(32166), s)
        elif utilities.isShow(media_type):
            summaryInfo = {
                'shows': [{'ids': data['ids']}]}
            s = utilities.getFormattedItemName(media_type, data)
            logger.debug("doAddToWatchlist(): %s" % str(summaryInfo))

            result = globals.traktapi.addToWatchlist(summaryInfo)
            if result:
                kodiUtilities.notification(kodiUtilities.getString(32165), s)
            else:
                kodiUtilities.notification(kodiUtilities.getString(32166), s)

    def doMarkWatched(self, data):

        media_type = data['media_type']

        if utilities.isMovie(media_type):
            temp_ids, id_type = utilities.parseIdToTraktIds(
                str(utilities.best_id(data['ids'], media_type)), media_type)

            best_id = temp_ids[id_type]

            summaryInfo = globals.traktapi.getMovieSummary(
                best_id).to_dict()
            if summaryInfo:
                if not summaryInfo['watched']:
                    s = utilities.getFormattedItemName(media_type, summaryInfo)
                    logger.debug("doMarkWatched(): '%s' is not watched on Trakt, marking it as watched." % s)
                    params = {'movies': [summaryInfo]}
                    logger.debug("doMarkWatched(): %s" % str(params))

                    result = globals.traktapi.addToHistory(params)
                    if result:
                        kodiUtilities.notification(kodiUtilities.getString(32113), s)
                    else:
                        kodiUtilities.notification(kodiUtilities.getString(32114), s)
        elif utilities.isEpisode(media_type):
            summaryInfo = {'shows': [{'ids': data['ids'], 'seasons': [
                {'number': data['season'], 'episodes': [{'number': data['number']}]}]}]}
            logger.debug("doMarkWatched(): %s" % str(summaryInfo))
            s = utilities.getFormattedItemName(media_type, data)

            result = globals.traktapi.addToHistory(summaryInfo)
            if result:
                kodiUtilities.notification(kodiUtilities.getString(32113), s)
            else:
                kodiUtilities.notification(kodiUtilities.getString(32114), s)
        elif utilities.isSeason(media_type):
            summaryInfo = {'shows': [{'ids': data['ids'], 'seasons': [
                {'number': data['season'], 'episodes': []}]}]}
            s = utilities.getFormattedItemName(media_type, data)
            for ep in data['episodes']:
                summaryInfo['shows'][0]['seasons'][0]['episodes'].append({
                                                                         'number': ep})

            logger.debug("doMarkWatched(): '%s - Season %d' has %d episode(s) that are going to be marked as watched." % (data['id'], data['season'], len(summaryInfo['shows'][0]['seasons'][0]['episodes'])))

            self.addEpisodesToHistory(summaryInfo, s)

        elif utilities.isShow(media_type):
            summaryInfo = {'shows': [{'ids': data['ids'], 'seasons': []}]}
            if summaryInfo:
                s = utilities.getFormattedItemName(media_type, data)
                logger.debug('data: %s' % data)
                for season in data['seasons']:
                    episodeJson = []
                    for episode in data['seasons'][season]:
                        episodeJson.append({'number': episode})
                    summaryInfo['shows'][0]['seasons'].append({'number': season, 'episodes': episodeJson})

                self.addEpisodesToHistory(summaryInfo, s)

    def addEpisodesToHistory(self, summaryInfo, s):
        if len(summaryInfo['shows'][0]['seasons'][0]['episodes']) > 0:
            logger.debug("doMarkWatched(): %s" % str(summaryInfo))

            result = globals.traktapi.addToHistory(summaryInfo)
            if result:
                kodiUtilities.notification(kodiUtilities.getString(32113), kodiUtilities.getString(32115) % (result['added']['episodes'], s))
            else:
                kodiUtilities.notification(kodiUtilities.getString(32114), s)

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

    def onNotification(self, sender, method, data):
        if method.split('.')[1].upper() != 'NEXTUPWATCHEDSIGNAL': # method looks like Other.NEXTUPWATCHEDSIGNAL
            return

        logger.debug('Callback received - Upnext skipped to the next episode')
        data = {'action': 'ended'}
        self.action(data)

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
    def onAVStarted(self):
        xbmc.sleep(1000)
        self.type = None
        self.id = None

        # take the user start scrobble offset into account
        scrobbleStartOffset = kodiUtilities.getSettingAsInt('scrobble_start_offset')*60
        if scrobbleStartOffset > 0:
            waitFor = 10
            waitedFor = 0
            # check each 10 seconds if we can abort or proceed
            while scrobbleStartOffset > waitedFor:
                waitedFor += waitFor
                time.sleep(waitFor)
                if not self.isPlayingVideo():
                    logger.debug('[traktPlayer] Playback stopped before reaching the scrobble offset')
                    return

        # only do anything if we're playing a video
        if self.isPlayingVideo():
            # get item data from json rpc
            activePlayers = kodiUtilities.kodiJsonRequest({"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1})
            logger.debug("[traktPlayer] onAVStarted() - activePlayers: %s" % activePlayers)
            playerId = int(activePlayers[0]['playerid'])
            logger.debug("[traktPlayer] onAVStarted() - Doing Player.GetItem kodiJsonRequest")
            result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'Player.GetItem', 'params': {'playerid': playerId}, 'id': 1})
            if result:
                logger.debug("[traktPlayer] onAVStarted() - %s" % result)
                # check for exclusion
                _filename = None
                try:
                    _filename = self.getPlayingFile()
                except:
                    logger.debug("[traktPlayer] onAVStarted() - Exception trying to get playing filename, player suddenly stopped.")
                    return

                if kodiUtilities.checkExclusion(_filename):
                    logger.debug("[traktPlayer] onAVStarted() - '%s' is in exclusion settings, ignoring." % _filename)
                    return

                if (kodiUtilities.getSettingAsBool('scrobble_mythtv_pvr')):
                    logger.debug('[traktPlayer] Setting is enabled to try scrobbling mythtv pvr recording, if necessary.')

                self.type = result['item']['type']
                data = {'action': 'started'}
                # check type of item
                if 'id' not in result['item'] or self.type == 'channel':
                    # get non-library details by infolabel (ie. PVR, plugins, etc.)
                    self.type, data = kodiUtilities.getInfoLabelDetails(result)
                elif self.type == 'episode' or self.type == 'movie':
                    # get library id
                    self.id = result['item']['id']
                    data['id'] = self.id
                    data['type'] = self.type

                    if self.type == 'episode':
                        logger.debug("[traktPlayer] onAVStarted() - Doing multi-part episode check.")
                        result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodeDetails', 'params': {'episodeid': self.id, 'properties': ['tvshowid', 'season', 'episode', 'file']}, 'id': 1})
                        if result:
                            logger.debug("[traktPlayer] onAVStarted() - %s" % result)
                            tvshowid = int(result['episodedetails']['tvshowid'])
                            season = int(result['episodedetails']['season'])
                            currentfile = result['episodedetails']['file']

                            result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': tvshowid, 'season': season, 'properties': ['episode', 'file'], 'sort': {'method': 'episode'}}, 'id': 1})
                            if result:
                                logger.debug("[traktPlayer] onAVStarted() - %s" % result)
                                # make sure episodes array exists in results
                                if 'episodes' in result:
                                    multi = []
                                    for i in range(result['limits']['start'], result['limits']['total']):
                                        if currentfile == result['episodes'][i]['file']:
                                            multi.append(result['episodes'][i]['episodeid'])
                                    if len(multi) > 1:
                                        data['multi_episode_data'] = multi
                                        data['multi_episode_count'] = len(multi)
                                        logger.debug("[traktPlayer] onAVStarted() - This episode is part of a multi-part episode.")
                                    else:
                                        logger.debug("[traktPlayer] onAVStarted() - This is a single episode.")
                elif (kodiUtilities.getSettingAsBool('scrobble_mythtv_pvr') and self.type == 'unknown' and result['item']['label']):
                    # If we have label/id but no show type, then this might be a PVR recording.

                    # DEBUG INFO: This code is useful when trying to figure out what info is available. Many of the fields
                    # that you'd expect (TVShowTitle, episode, season, etc) are always blank. In Kodi v15, we got the show
                    # and episode name in the VideoPlayer label. In v16, that's gone, but the Player.Filename infolabel
                    # is populated with several interesting things. If these things change in future versions, uncommenting
                    # this code will hopefully provide some useful info in the debug log.
                    #logger.debug("[traktPlayer] onAVStarted() - TEMP Checking all videoplayer infolabels.")
                    #for il in ['VideoPlayer.Time','VideoPlayer.TimeRemaining','VideoPlayer.TimeSpeed','VideoPlayer.Duration','VideoPlayer.Title','VideoPlayer.TVShowTitle','VideoPlayer.Season','VideoPlayer.Episode','VideoPlayer.Genre','VideoPlayer.Director','VideoPlayer.Country','VideoPlayer.Year','VideoPlayer.Rating','VideoPlayer.UserRating','VideoPlayer.Votes','VideoPlayer.RatingAndVotes','VideoPlayer.mpaa',VideoPlayer.EpisodeName','VideoPlayer.PlaylistPosition','VideoPlayer.PlaylistLength','VideoPlayer.Cast','VideoPlayer.CastAndRole','VideoPlayer.Album','VideoPlayer.Artist','VideoPlayer.Studio','VideoPlayer.Writer','VideoPlayer.Tagline','VideoPlayer.PlotOutline','VideoPlayer.Plot','VideoPlayer.LastPlayed','VideoPlayer.PlayCount','VideoPlayer.VideoCodec','VideoPlayer.VideoResolution','VideoPlayer.VideoAspect','VideoPlayer.AudioCodec','VideoPlayer.AudioChannels','VideoPlayer.AudioLanguage','VideoPlayer.SubtitlesLanguage','VideoPlayer.StereoscopicMode','VideoPlayer.EndTime','VideoPlayer.NextTitle','VideoPlayer.NextGenre','VideoPlayer.NextPlot','VideoPlayer.NextPlotOutline','VideoPlayer.NextStartTime','VideoPlayer.NextEndTime','VideoPlayer.NextDuration','VideoPlayer.ChannelName','VideoPlayer.ChannelNumber','VideoPlayer.SubChannelNumber','VideoPlayer.ChannelNumberLabel','VideoPlayer.ChannelGroup','VideoPlayer.ParentalRating','Player.FinishTime','Player.FinishTime(format)','Player.Chapter','Player.ChapterCount','Player.Time','Player.Time(format)','Player.TimeRemaining','Player.TimeRemaining(format)','Player.Duration','Player.Duration(format)','Player.SeekTime','Player.SeekOffset','Player.SeekOffset(format)','Player.SeekStepSize','Player.ProgressCache','Player.Folderpath','Player.Filenameandpath','Player.StartTime','Player.StartTime(format)','Player.Title','Player.Filename']:
                    #    logger.debug("[traktPlayer] TEMP %s : %s" % (il, xbmc.getInfoLabel(il)))
                    #for k,v in result.items():
                    #    logger.debug("[traktPlayer] onAVStarted() - result - %s : %s" % (k,v))
                    #for k,v in result['item'].items():
                    #    logger.debug("[traktPlayer] onAVStarted() - result.item - %s : %s" % (k,v))

                    # As of Kodi v17, many of the VideoPlayer labels are populated by the MythTV PVR addon, though sadly this
                    # does not include IMDB number. That means we're still stuck using the show title/episode name to look up
                    # IDs to feed to the scrobbler. Still, much easier than previous versions!
                    foundShowName = xbmc.getInfoLabel('VideoPlayer.Title')
                    logger.debug("[traktPlayer] onAVStarted() - Found VideoPlayer.Title: %s" % foundShowName)
                    foundEpisodeName = xbmc.getInfoLabel('VideoPlayer.EpisodeName')
                    logger.debug("[traktPlayer] onAVStarted() - Found VideoPlayer.EpisodeName: %s" % foundEpisodeName)
                    foundEpisodeYear = xbmc.getInfoLabel('VideoPlayer.Year')
                    logger.debug("[traktPlayer] onAVStarted() - Found VideoPlayer.Year: %s" % foundEpisodeYear)
                    foundSeason = xbmc.getInfoLabel('VideoPlayer.Season')
                    logger.debug("[traktPlayer] onAVStarted() - Found VideoPlayer.Season: %s" % foundSeason)
                    foundEpisode = xbmc.getInfoLabel('VideoPlayer.Episode')
                    logger.debug("[traktPlayer] onAVStarted() - Found VideoPlayer.Episode: %s" % foundEpisode)
                    if (foundShowName and foundEpisodeName and foundEpisodeYear):
                        # If the show/episode/year are populated, we can skip all the mess of trying to extract the info from the 
                        # Player.Filename infolabel.
                        logger.debug("[traktPlayer] onAVStarted() - Got info from VideoPlayer labels")
                    else:
                        logger.debug("[traktPlayer] onAVStarted() - No love from VideoPlayer labels, trying Player.Filename infolabel")
                        # If that didn't work, we can fall back on the Player.Filename infolabel. It shows up like this:
                        # (v16) ShowName [sXXeYY ](year) EpisodeName, channel, PVRFileName
                        # (v17) ShowName [sXXeYY ](year) EpisodeName, channel, date, PVRFileName
                        # The season and episode info may or may not be present. Also, sometimes there are some URL encodings
                        # (i.e. %20 instead of space) so those need removing. For example:
                        # Powerless s01e08 (2017)%20Green%20Furious, TV%20(WOOD%20TV), 20170414_003000, 1081_1492129800_4e1.pvr
                        # DC's Legends of Tomorrow (2016) Pilot, Part 2, TV (CW W MI), 20160129_010000, 1081_1492129800_4e1.pvr
                        foundLabel = urllib.unquote(xbmc.getInfoLabel('Player.Filename'))
                        logger.debug("[traktPlayer] onAVStarted() - Found unknown video type with label: %s. Might be a PVR episode, searching Trakt for it." % foundLabel)
                        logger.debug("[traktPlayer] onAVStarted() - After urllib.unquote: %s." % foundLabel)
                        splitLabel = foundLabel.rsplit(", ", 3)
                        logger.debug("[traktPlayer] onAVStarted() - Post-split of label: %s " % splitLabel)
                        if len(splitLabel) != 4:
                            logger.debug("[traktPlayer] onAVStarted() - Label doesn't have the ShowName sXXeYY (year) EpisodeName, channel, date, PVRFileName format that was expected. Might be the v16 version with no date instead.")
                            splitLabel = foundLabel.rsplit(", ", 2)
                            logger.debug("[traktPlayer] onAVStarted() - Post-split of label: %s " % splitLabel)
                            if len(splitLabel) != 3:
                                logger.debug("[traktPlayer] onAVStarted() - Label doesn't have the ShowName sXXeYY (year) EpisodeName, channel, PVRFileName format that was expected. Giving up.")
                                return
                        foundShowAndEpInfo = splitLabel[0]
                        logger.debug("[traktPlayer] onAVStarted() - show plus episode info: %s" % foundShowAndEpInfo)
                        splitShowAndEpInfo = re.split(r' (s\d\de\d\d)? ?\((\d\d\d\d)\) ', foundShowAndEpInfo, 1)
                        logger.debug("[traktPlayer] onAVStarted() - Post-split of show plus episode info: %s " % splitShowAndEpInfo)
                        if len(splitShowAndEpInfo) != 4:
                            logger.debug("[traktPlayer] onAVStarted() - Show plus episode info doesn't have the ShowName sXXeYY (year) EpisodeName format that was expected. Giving up.")
                            return
                        foundShowName = splitShowAndEpInfo[0]
                        logger.debug("[traktPlayer] onAVStarted() - using show name: %s" % foundShowName)
                        foundEpisodeName = splitShowAndEpInfo[3]
                        logger.debug("[traktPlayer] onAVStarted() - using episode name: %s" % foundEpisodeName)
                        foundEpisodeYear = splitShowAndEpInfo[2]
                        logger.debug("[traktPlayer] onAVStarted() - using episode year: %s" % foundEpisodeYear)
                    epYear = None
                    try:
                        epYear = int(foundEpisodeYear)
                    except ValueError:
                        epYear = None
                    logger.debug("[traktPlayer] onAVStarted() - verified episode year: %d" % epYear)
                    # All right, now we have the show name, episode name, and (maybe) episode year. All good, but useless for
                    # scrobbling since Trakt only understands IDs, not names.
                    data['video_ids'] = None
                    data['season'] = None
                    data['episode'] = None
                    data['episodeTitle'] = None
                    # First thing to try, a text query to the Trakt DB looking for this episode. Note
                    # that we can't search for show and episode together, because the Trakt function gets confused and returns nothing.
                    newResp = globals.traktapi.getTextQuery(foundEpisodeName, "episode", epYear)
                    if not newResp:
                        logger.debug("[traktPlayer] onAVStarted() - Empty Response from getTextQuery, giving up")
                    else:
                        logger.debug("[traktPlayer] onAVStarted() - Got Response from getTextQuery: %s" % str(newResp))
                        # We got something back. See if one of the returned values is for the show we're looking for. Often it's
                        # not, but since there's no way to tell the search which show we want, this is all we can do.
                        rightResp = None
                        for thisResp in newResp:
                            compareShowName = thisResp.show.title
                            logger.debug("[traktPlayer] onAVStarted() - comparing show name: %s" % compareShowName)
                            if thisResp.show.title == foundShowName:
                                logger.debug("[traktPlayer] onAVStarted() - found the right show, using this response")
                                rightResp = thisResp
                                break
                        if rightResp is None:
                            logger.debug("[traktPlayer] onAVStarted() - Failed to find matching episode/show via text search.")
                        else:
                            # OK, now we have a episode object to work with.
                            self.type = 'episode'
                            data['type'] = 'episode'
                            # You'd think we could just use the episode key that Trakt just returned to us, but the scrobbler
                            # function (see scrobber.py) only understands the show key plus season/episode values.
                            showKeys = { }
                            for eachKey in rightResp.show.keys:
                                showKeys[eachKey[0]] = eachKey[1]
                            data['video_ids'] = showKeys
                            # For some reason, the Trakt search call returns the season and episode as an array in the pk field.
                            # You'd think individual episode and season fields would be better, but whatever.
                            data['season'] = rightResp.pk[0]
                            data['episode'] = rightResp.pk[1]
                    # At this point if we haven't found the episode data yet, the episode-title-text-search method
                    # didn't work.
                    if (not data['season']):
                        # This text query API is basically the same as searching on the website. Works with alternative
                        # titles, unlike the scrobble function. Though we can't use the episode year since that would only
                        # match the show if we're dealing with season 1.
                        logger.debug("[traktPlayer] onAVStarted() - Searching for show title via getTextQuery: %s" % foundShowName)
                        newResp = globals.traktapi.getTextQuery(foundShowName, "show", None)
                        if not newResp:
                            logger.debug("[traktPlayer] onAVStarted() - Empty Show Response from getTextQuery, falling back on episode text query")
                        else:
                            logger.debug("[traktPlayer] onAVStarted() - Got Show Response from getTextQuery: %s" % str(newResp))
                            # We got something back. Have to assume the first show found is the right one; if there's more than
                            # one, there's no way to know which to use. Pull the ids from the show data, and store 'em for scrobbling.
                            showKeys = { }
                            for eachKey in newResp[0].keys:
                                showKeys[eachKey[0]] = eachKey[1]
                            data['video_ids'] = showKeys
                            # Now to find the episode. There's no search function to look for an episode within a show, but
                            # we can get all the episodes and look for the title.
                            while (not data['season']):
                                logger.debug("[traktPlayer] onAVStarted() - Querying for all seasons/episodes of this show")
                                epQueryResp = globals.traktapi.getShowWithAllEpisodesList(data['video_ids']['trakt'])
                                if not epQueryResp:
                                    # Nothing returned. Giving up.
                                    logger.debug("[traktPlayer] onAVStarted() - No response received")
                                    break
                                else:
                                    # Got the list back. Go through each season.
                                    logger.debug("[traktPlayer] onAVStarted() - Got response with seasons: %s" % str(epQueryResp))
                                    for eachSeason in epQueryResp:
                                        # For each season, check each episode.
                                        logger.debug("[traktPlayer] onAVStarted() - Processing season: %s" % str(eachSeason))
                                        for eachEpisodeNumber in eachSeason.episodes:
                                            thisEpTitle = None
                                            # Get the title. The try block is here in case the title doesn't exist for some entries.
                                            try:
                                                thisEpTitle = eachSeason.episodes[eachEpisodeNumber].title
                                            except:
                                                thisEpTitle = None
                                            logger.debug("[traktPlayer] onAVStarted() - Checking episode number %d with title %s" % (eachEpisodeNumber, thisEpTitle))
                                            if (foundEpisodeName == thisEpTitle):
                                                # Found it! Save the data. The scrobbler wants season and episode number. Which for some
                                                # reason is stored as a pair in the first item in the keys array.
                                                data['season'] = eachSeason.episodes[eachEpisodeNumber].keys[0][0]
                                                data['episode'] = eachSeason.episodes[eachEpisodeNumber].keys[0][1]
                                                # Title too, just for the heck of it. Though it's not actually used.
                                                data['episodeTitle'] = thisEpTitle
                                                break
                                        # If we already found our data, no need to go through the rest of the seasons.
                                        if (data['season']):
                                            break
                    # Now we've done all we can.
                    if (data['season']):
                        # OK, that's everything. Data should be all set for scrobbling.
                        logger.debug("[traktPlayer] onAVStarted() - Playing a non-library 'episode' : show trakt key %s, season: %d, episode: %d" % (data['video_ids'], data['season'], data['episode']))
                    else:
                        # Still no data? Too bad, have to give up.
                        logger.debug("[traktPlayer] onAVStarted() - Did our best, but couldn't get info for this show and episode. Skipping.")
                        return
                else:
                    logger.debug("[traktPlayer] onAVStarted() - Video type '%s' unrecognized, skipping." % self.type)
                    return

                pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                plSize = len(pl)
                if plSize > 1:
                    pos = pl.getposition()
                    if not self.plIndex is None:
                        logger.debug("[traktPlayer] onAVStarted() - User manually skipped to next (or previous) video, forcing playback ended event.")
                        self.onPlayBackEnded()
                    self.plIndex = pos
                    logger.debug("[traktPlayer] onAVStarted() - Playlist contains %d item(s), and is currently on item %d" % (plSize, (pos + 1)))

                self._playing = True

                # send dispatch
                self.action(data)

    # called when kodi stops playing a file
    def onPlayBackEnded(self):
        xbmcgui.Window(10000).clearProperty('script.trakt.ids')
        xbmcgui.Window(10000).clearProperty('script.trakt.paused')
        if self._playing:
            logger.debug("[traktPlayer] onPlayBackEnded() - %s" % self.isPlayingVideo())
            self._playing = False
            self.plIndex = None
            data = {'action': 'ended'}
            self.action(data)

    # called when user stops kodi playing a file
    def onPlayBackStopped(self):
        xbmcgui.Window(10000).clearProperty('script.trakt.ids')
        xbmcgui.Window(10000).clearProperty('script.trakt.paused')
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
