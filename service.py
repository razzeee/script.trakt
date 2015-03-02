# -*- coding: utf-8 -*-
import threading
from time import time
import logging
import xbmc

from traktapi import traktAPI

import globals
from rating import rateMedia
from scrobbler import Scrobbler
import sqliteQueue
from sync import Sync
import utilities

logger = logging.getLogger(__name__)

class traktService:
	scrobbler = None
	updateTagsThread = None
	syncThread = None
	dispatchQueue = sqliteQueue.SqliteQueue()
	
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
			elif action == 'databaseUpdated':
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
			elif action == 'manualSync':
				if not self.syncThread.isAlive():
					logger.debug("Performing a manual sync.")
					self.doSync(manual=True, silent=data['silent'], library=data['library'])
				else:
					logger.debug("There already is a sync in progress.")
			elif action == 'settings':
				utilities.showSettings()
			elif action == 'scanStarted':
				pass
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
		self.Player = traktPlayer(action = self._dispatchQueue)
		self.Monitor = traktMonitor(action = self._dispatchQueue)

		# init traktapi class
		globals.traktapi = traktAPI()

		# init sync thread
		self.syncThread = syncThread()

		# init scrobbler class
		self.scrobbler = Scrobbler(globals.traktapi)

		# start loop for events
		while not xbmc.abortRequested:
			while len(self.dispatchQueue) and (not xbmc.abortRequested):
				data = self.dispatchQueue.get()
				logger.debug("Queued dispatch: %s" % data)
				self._dispatch(data)

			if xbmc.Player().isPlayingVideo():
				self.scrobbler.update()

			xbmc.sleep(500)

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
			
		if 'dbid' in data:
			logger.debug("Getting data for manual %s of library '%s' with ID of '%s'" % (action, media_type, data['dbid']))
		elif 'remoteitd' in data:
			if 'season' in data:
				logger.debug("Getting data for manual %s of non-library '%s' S%02dE%02d, with ID of '%s'." % (action, media_type, data['season'], data['episode'], data['remoteid']))
			else:
				logger.debug("Getting data for manual %s of non-library '%s' with ID of '%s'" % (action, media_type, data['remoteid']))

		if utilities.isEpisode(media_type):
			summaryInfo = globals.traktapi.getEpisodeSummary(data['trakt'], data['season'], data['episode'])
		elif utilities.isShow(media_type):
			summaryInfo = globals.traktapi.getShowSummary(data['imdbnumber'])
		elif utilities.isMovie(media_type):
			summaryInfo = globals.traktapi.getMovieSummary(data['imdbnumber'])
		
		if not summaryInfo is None:
			if utilities.isMovie(media_type) or utilities.isShow(media_type):
				summaryInfo['xbmc_id'] = data['dbid']

			if action == 'rate':
				if not 'rating' in data:
					rateMedia(media_type, summaryInfo)
				else:
					rateMedia(media_type, summaryInfo, rating=data['rating'])
		else:
			logger.debug("doManualRating(): Summary info was empty, possible problem retrieving data from trakt.tv")

	def doMarkWatched(self, data):

		media_type = data['media_type']
		markedNotification = utilities.getSettingAsBool('show_marked_notification')
		
		if utilities.isMovie(media_type):
			summaryInfo = globals.traktapi.getMovieSummary(data['id'])
			if summaryInfo:
				if not summaryInfo['watched']:
					s = utilities.getFormattedItemName(media_type, summaryInfo)
					logger.debug("doMarkWatched(): '%s' is not watched on trakt, marking it as watched." % s)
					movie = {'imdb_id': data['id'], 'title': summaryInfo['title'], 'year': summaryInfo['year'],
					         'plays': 1, 'last_played': int(time())}
					params = {'movies': [movie]}
					logger.debug("doMarkWatched(): %s" % str(params))
					

					result = globals.traktapi.updateSeenMovie(params)
					if result:
						if markedNotification:
							utilities.notification(utilities.getString(32113), s)
					else:
						utilities.notification(utilities.getString(32114), s)

					
		elif utilities.isEpisode(media_type):
			summaryInfo = globals.traktapi.getEpisodeSummary(data['id'], data['season'], data['episode'])
			if summaryInfo:
				if not summaryInfo['episode']['watched']:
					s = utilities.getFormattedItemName(media_type, summaryInfo)
					logger.debug("doMarkWathced(): '%s' is not watched on trakt, marking it as watched." % s)
					params = {'imdb_id': summaryInfo['ids']['imdb_id'], 'tvdb_id': summaryInfo['ids']['tvdb_id'],
					          'title': summaryInfo['title'], 'year': summaryInfo['year'],
					          'episodes': [{'season': data['season'], 'episode': data['episode']}]}
					logger.debug("doMarkWatched(): %s" % str(params))
					

					result = globals.traktapi.updateSeenEpisode(params)
					if result:
						if markedNotification:
							utilities.notification(utilities.getString(32113), s)
					else:
						utilities.notification(utilities.getString(32114), s)

		elif utilities.isSeason(media_type):
			showInfo = globals.traktapi.getShowSummary(data['id'])
			if not showInfo:
				return
			summaryInfo = globals.traktapi.getSeasonInfo(data['id'], data['season'])
			if summaryInfo:
				showInfo['season'] = data['season']
				s = utilities.getFormattedItemName(media_type, showInfo)
				params = {'imdb_id': summaryInfo['ids']['imdb'], 'tvdb_id': summaryInfo['ids']['tvdb'],
				          'title': showInfo['title'], 'year': showInfo['year'], 'episodes': []}
				for ep in summaryInfo:
					if ep['episode'] in data['episodes']:
						if not ep['watched']:
							params['episodes'].append({'season': ep['season'], 'episode': ep['episode']})

				logger.debug("doMarkWatched(): '%s - Season %d' has %d episode(s) that are going to be marked as watched." % (showInfo['title'], data['season'], len(params['episodes'])))
				
				if len(params['episodes']) > 0:
					logger.debug("doMarkWatched(): %s" % str(params))

					result = globals.traktapi.updateSeenEpisode(params)
					if result:
						if markedNotification:
							utilities.notification(utilities.getString(32113), utilities.getString(32115) % (len(params['episodes']), s))
					else:
						utilities.notification(utilities.getString(32114), utilities.getString(32115) % (len(params['episodes']), s))


		elif utilities.isShow(media_type):
			summaryInfo = globals.traktapi.getShowSummary(data['id'], extended=True)
			if summaryInfo:
				s = utilities.getFormattedItemName(media_type, summaryInfo)
				params = {'imdb_id': summaryInfo['ids']['imdb'], 'tvdb_id': summaryInfo['ids']['tvdb'],
				          'title': summaryInfo['title'], 'year': summaryInfo['year'], 'episodes': []}
				for season in summaryInfo['seasons']:
					for ep in season['episodes']:
						if str(season['season']) in data['seasons']:
							if ep['episode'] in data['seasons'][str(season['season'])]:
								if not ep['watched']:
									params['episodes'].append({'season': ep['season'], 'episode': ep['episode']})
				logger.debug("doMarkWatched(): '%s' has %d episode(s) that are going to be marked as watched." % (summaryInfo['title'], len(params['episodes'])))

				if len(params['episodes']) > 0:
					logger.debug("doMarkWatched(): %s" % str(params))

					result = globals.traktapi.updateSeenEpisode(params)
					if result:
						if markedNotification:
							utilities.notification(utilities.getString(32113), utilities.getString(32115) % (len(params['episodes']), s))
					else:
						utilities.notification(utilities.getString(32114), utilities.getString(32115) % (len(params['episodes']), s))


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
		xbmc.Monitor.__init__(self)
		self.action = kwargs['action']
		# xbmc.getCondVisibility('Library.IsScanningVideo') returns false when cleaning during update...
		self.scanning_video = False
		logger.debug("[traktMonitor] Initalized.")

	# called when database gets updated and return video or music to indicate which DB has been changed
	def onDatabaseUpdated(self, database):
		if database == 'video':
			self.scanning_video = False
			logger.debug("[traktMonitor] onDatabaseUpdated(database: %s)" % database)
			data = {'action': 'databaseUpdated'}
			self.action(data)

	# called when database update starts and return video or music to indicate which DB is being updated
	def onDatabaseScanStarted(self, database):
		if database == "video":
			self.scanning_video = True
			logger.debug("[traktMonitor] onDatabaseScanStarted(database: %s)" % database)
			data = {'action': 'scanStarted'}
			self.action(data)

	def onSettingsChanged(self):
		data = {'action': 'settingsChanged'}
		self.action(data)

	# Generic notification handler.  Only available in Gotham and later.
	def onNotification(self, sender, method, data):
		# onCleanFinished callback is only available in Helix and later.
		if method == 'VideoLibrary.OnCleanFinished' and not self.scanning_video: # Ignore clean on update.
			data = {'action': 'databaseCleaned'}
			self.action(data)

class traktPlayer(xbmc.Player):

	_playing = False
	plIndex = None

	def __init__(self, *args, **kwargs):
		xbmc.Player.__init__(self)
		self.action = kwargs['action']
		logger.debug("[traktPlayer] Initalized.")

	# called when kodi starts playing a file
	def onPlayBackStarted(self):
		xbmc.sleep(1000)
		self.type = None
		self.id = None

		# only do anything if we're playing a video
		if self.isPlayingVideo():
			# get item data from json rpc
			result = utilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'Player.GetItem', 'params': {'playerid': 1}, 'id': 1})
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

			try:
				self.id = result['item']['id']
                _idchecker=True
            except:
				#dont have an id, not library item
                _idchecker=False

            data = {'action': 'started'}

			# check type of item
			if self.type == 'unknown' or _idchecker==False:
				# do a deeper check to see if we have enough data to perform scrobbles
				logger.debug("[traktPlayer] onPlayBackStarted() - Started playing a non-library file, checking available data.")
				
				season = xbmc.getInfoLabel('VideoPlayer.Season')
				episode = xbmc.getInfoLabel('VideoPlayer.Episode')
				showtitle = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
				year = xbmc.getInfoLabel('VideoPlayer.Year')
				
				logger.debug("[traktPlayer] info - showtitle: %s, Year: %s, Season: %s, Episode: %s"  % (showtitle, year, season, episode))

				if season and episode and showtitle:
					# we have season, episode and show title, can scrobble this as an episode
					self.type = 'episode'
					data['type'] = 'episode'
					data['season'] = int(season)
					data['episode'] = int(episode)
					data['showtitle'] = showtitle
					data['title'] = xbmc.getInfoLabel('VideoPlayer.Title')
					if year.isdigit():
						data['year'] = year
					logger.debug("[traktPlayer] onPlayBackStarted() - Playing a non-library 'episode' - %s - S%02dE%02d - %s." % (data['showtitle'], data['season'], data['episode'], data['title']))
				elif year and not season and not showtitle:
					# we have a year and no season/showtitle info, enough for a movie
					self.type = 'movie'
					data['type'] = 'movie'
					data['year'] = int(year)
					data['title'] = xbmc.getInfoLabel('VideoPlayer.Title')
					logger.debug("[traktPlayer] onPlayBackStarted() - Playing a non-library 'movie' - %s (%d)." % (data['title'], data['year']))
				elif showtitle:
					title, season, episode = utilities.regex_tvshow(False, showtitle)
					data['type'] = 'episode'
					data['season'] = int(season)
					data['episode'] = int(episode)
					data['showtitle'] = title
					data['title'] = title
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
					result = utilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodeDetails', 'params': {'episodeid': self.id, 'properties': ['tvshowid', 'season', 'episode']}, 'id': 1})
					if result:
						logger.debug("[traktPlayer] onPlayBackStarted() - %s" % result)
						tvshowid = int(result['episodedetails']['tvshowid'])
						season = int(result['episodedetails']['season'])
						episode = int(result['episodedetails']['episode'])
						episode_index = episode - 1

						result = utilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': tvshowid, 'season': season, 'properties': ['episode', 'file'], 'sort': {'method': 'episode'}}, 'id': 1})
						if result:
							logger.debug("[traktPlayer] onPlayBackStarted() - %s" % result)
							# make sure episodes array exists in results
							if 'episodes' in result:
								multi = []
								for i in range(episode_index, result['limits']['total']):
									if result['episodes'][i]['file'] == result['episodes'][episode_index]['file']:
										multi.append(result['episodes'][i]['episodeid'])
									else:
										break
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
		if self._playing:
			logger.debug("[traktPlayer] onPlayBackEnded() - %s" % self.isPlayingVideo())
			self._playing = False
			self.plIndex = None
			data = {'action': 'ended'}
			self.action(data)

	# called when user stops kodi playing a file
	def onPlayBackStopped(self):
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
