# -*- coding: utf-8 -*-
#

import xbmc
import time

import utilities
from utilities import Debug
from rating import ratingCheck

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
	markedAsWatched = []
	traktSummaryInfo = None
	traktShowSummary = None

	def __init__(self, api):
		self.traktapi = api

	def _currentEpisode(self, watchedPercent, episodeCount):
		split = (100 / episodeCount)
		for i in range(episodeCount - 1, 0, -1):
			if watchedPercent >= (i * split):
				return i
		return 0

	def update(self, forceCheck = False):
		if not xbmc.Player().isPlayingVideo():
			return

		if self.isPlaying:
			t = xbmc.Player().getTime()
			l = xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition()
			if self.playlistIndex == l:
				self.watchedTime = t
			else:
				Debug("[Scrobbler] Current playlist item changed! Not updating time! (%d -> %d)" % (self.playlistIndex, l))

			if 'id' in self.curVideo and self.isMultiPartEpisode:
				# do transition check every minute
				if (time.time() > (self.lastMPCheck + 60)) or forceCheck:
					self.lastMPCheck = time.time()
					watchedPercent = (self.watchedTime / self.videoDuration) * 100
					epIndex = self._currentEpisode(watchedPercent, self.curVideo['multi_episode_count'])
					if self.curMPEpisode != epIndex:
						# current episode in multi-part episode has changed
						Debug("[Scrobbler] Attempting to scrobble episode part %d of %d." % (self.curMPEpisode + 1, self.curVideo['multi_episode_count']))

						# recalculate watchedPercent and duration for multi-part, and scrobble
						adjustedDuration = int(self.videoDuration / self.curVideo['multi_episode_count'])
						watchedPercent = ((self.watchedTime - (adjustedDuration * self.curMPEpisode)) / adjustedDuration) * 100
						response = self.traktapi.scrobbleEpisode(self.traktShowSummary, self.traktSummaryInfo, watchedPercent)
						if response != None:
							Debug("[Scrobbler] Scrobble response: %s" % str(response))

						# update current information
						self.curMPEpisode = epIndex
						self.curVideoInfo = utilities.getEpisodeDetailsFromKodi(self.curVideo['multi_episode_data'][self.curMPEpisode], ['showtitle', 'season', 'episode', 'tvshowid', 'uniqueid'])


	def playbackStarted(self, data):
		Debug("[Scrobbler] playbackStarted(data: %s)" % data)
		if not data:
			return
		self.curVideo = data
		self.curVideoInfo = None

		if 'type' in self.curVideo:
			Debug("[Scrobbler] Watching: %s" % self.curVideo['type'])
			if not xbmc.Player().isPlayingVideo():
				Debug("[Scrobbler] Suddenly stopped watching item")
				return
			xbmc.sleep(1000) # Wait for possible silent seek (caused by resuming)
			try:
				self.watchedTime = xbmc.Player().getTime()
				self.videoDuration = xbmc.Player().getTotalTime()
			except Exception as e:
				Debug("[Scrobbler] Suddenly stopped watching item: %s" % e.message)
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
			if (self.playlistLength == 0):
				Debug("[Scrobbler] Warning: Cant find playlist length, assuming that this item is by itself")
				self.playlistLength = 1

			self.traktSummaryInfo = None
			self.isMultiPartEpisode = False
			if utilities.isMovie(self.curVideo['type']):
				if 'id' in self.curVideo:
					self.curVideoInfo = utilities.kodiRpcToTraktMediaObject('movie', utilities.getMovieDetailsFromKodi(self.curVideo['id'], ['imdbnumber', 'title', 'year', 'file', 'lastplayed', 'playcount']))
					Debug("Trakt ticket: %s" % self.curVideo)
					if utilities.getSettingAsBool('rate_movie'):
						# pre-get sumamry information, for faster rating dialog.
						Debug("[Scrobbler] Movie rating is enabled, pre-fetching summary information.")
						if self.curVideoInfo['ids']['imdb']:
							self.traktSummaryInfo = self.traktapi.getMovieSummary(self.curVideoInfo['ids']['imdb'])
						elif self.curVideoInfo['ids']['tmdb']:
							self.traktSummaryInfo = self.traktapi.getMovieSummary(self.curVideoInfo['ids']['tmdb'])
						else:
							self.curVideoInfo['ids']['imdb'] = None
							Debug("[Scrobbler] Can not get summary information for '%s (%d)' as is has no valid id, will retry during a watching call." % (self.curVideoInfo['title'], self.curVideoInfo['year']))
				elif 'title' in self.curVideo and 'year' in self.curVideo:
					self.curVideoInfo = {'ids': {}}
					self.curVideoInfo['ids']['imdb'] = None
					self.curVideoInfo['title'] = self.curVideo['title']
					self.curVideoInfo['year'] = self.curVideo['year']

			elif utilities.isEpisode(self.curVideo['type']):
				if 'id' in self.curVideo:
					episodeDetailsKodi = utilities.getEpisodeDetailsFromKodi(self.curVideo['id'], ['showtitle', 'season', 'episode', 'tvshowid', 'uniqueid', 'file', 'playcount'])
					tvdb = episodeDetailsKodi['imdbnumber']
					self.curVideoInfo = utilities.kodiRpcToTraktMediaObject('episode', episodeDetailsKodi)
					if not self.curVideoInfo: # getEpisodeDetailsFromKodi was empty
						Debug("[Scrobbler] Episode details from Kodi was empty, ID (%d) seems invalid, aborting further scrobbling of this episode." % self.curVideo['id'])
						self.curVideo = None
						self.isPlaying = False
						self.watchedTime = 0
						return
					#if utilities.getSettingAsBool('rate_episode'):
						# pre-get sumamry information, for faster rating dialog.
					#	Debug("[Scrobbler] Episode rating is enabled, pre-fetching summary information.")

                                        if tvdb:
                                                lookupShow = self.traktapi.getIdLookup('tvdb', tvdb)
                                                self.traktShowSummary = self.traktapi.getShowSummary(lookupShow['ids']['slug'])
                                                self.traktSummaryInfo = self.traktapi.getEpisodeSummary(lookupShow['ids'], self.curVideoInfo['season'], self.curVideoInfo['number'])
                                        else:
                                                Debug("[Scrobbler] Can not get summary information for '%s - S%02dE%02d' as it has no valid id, will retry during a watching call." % (self.curVideoInfo['showtitle'], self.curVideoInfo['season'], self.curVideoInfo['episode']))
				elif 'title' in self.curVideo and 'season' in self.curVideo and 'episode' in self.curVideo:
					self.curVideoInfo = {'tvdb_id': None}
					self.curVideoInfo['title'] = self.curVideo['title']
					self.curVideoInfo['season'] = self.curVideo['season']
					self.curVideoInfo['number'] = self.curVideo['episode']

					self.traktShowSummary = {'title': self.curVideo['showtitle']}
					if 'year' in self.curVideo:
						self.traktShowSummary['year'] = self.curVideo['year']

				if 'multi_episode_count' in self.curVideo:
					self.isMultiPartEpisode = True
					self.markedAsWatched = []
					episode_count = self.curVideo['multi_episode_count']
					for i in range(episode_count):
						self.markedAsWatched.append(False)

			self.isPlaying = True
			self.isPaused = False
			self.__scrobble('start')

	def playbackResumed(self):
		if not self.isPlaying:
			return

		Debug("[Scrobbler] playbackResumed()")
		if self.isPaused:
			p = time.time() - self.pausedAt
			Debug("[Scrobbler] Resumed after: %s" % str(p))
			self.pausedAt = 0
			self.isPaused = False
			self.update(True)
			self.__scrobble('start')

	def playbackPaused(self):
		if not self.isPlaying:
			return

		Debug("[Scrobbler] playbackPaused()")
		self.update(True)
		Debug("[Scrobbler] Paused after: %s" % str(self.watchedTime))
		self.isPaused = True
		self.pausedAt = time.time()
		self.__scrobble('pause')

	def playbackSeek(self):
		if not self.isPlaying:
			return

		Debug("[Scrobbler] playbackSeek()")
		self.update(True)
		self.__scrobble('start')

	def playbackEnded(self):
		if not self.isPlaying:
			return

		Debug("[Scrobbler] playbackEnded()")
		if self.curVideo == None:
			Debug("[Scrobbler] Warning: Playback ended but video forgotten.")
			return
		self.isPlaying = False
		self.markedAsWatched = []
		if self.watchedTime != 0:
			if 'type' in self.curVideo:
				self.__scrobble('stop')
				ratingCheck(self.curVideo['type'], self.traktSummaryInfo, self.watchedTime, self.videoDuration, self.playlistLength)
			self.watchedTime = 0
			self.isMultiPartEpisode = False
		self.traktSummaryInfo = None
		self.curVideo = None
		self.playlistLength = 0
		self.playlistIndex = 0


	def __scrobble(self, status):
		if not self.curVideoInfo:
			return

		Debug("[Scrobbler] scrobble()")
		scrobbleMovieOption = utilities.getSettingAsBool('scrobble_movie')
		scrobbleEpisodeOption = utilities.getSettingAsBool('scrobble_episode')

		watchedPercent = (self.watchedTime / self.videoDuration) * 100

		if utilities.isMovie(self.curVideo['type']) and scrobbleMovieOption:
			response = self.traktapi.scrobbleMovie(self.curVideoInfo, watchedPercent, status)
			if not response is None:
				self.__scrobbleNotification(response)
				Debug("[Scrobbler] Scrobble response: %s" % str(response))


		elif utilities.isEpisode(self.curVideo['type']) and scrobbleEpisodeOption:
			if self.isMultiPartEpisode:
				Debug("[Scrobbler] Multi-part episode, scrobbling part %d of %d." % (self.curMPEpisode + 1, self.curVideo['multi_episode_count']))
				adjustedDuration = int(self.videoDuration / self.curVideo['multi_episode_count'])
				watchedPercent = ((self.watchedTime - (adjustedDuration * self.curMPEpisode)) / adjustedDuration) * 100

			response = self.traktapi.scrobbleEpisode(self.traktShowSummary, self.curVideoInfo, watchedPercent, status)

			if not response is None:
				self.__scrobbleNotification(response)
				Debug("[Scrobbler] Scrobble response: %s" % str(response))


	def __scrobbleNotification(self, info):
		if not self.curVideoInfo:
			return
		
		if utilities.getSettingAsBool("scrobble_notification"):
			s = utilities.getFormattedItemName(self.curVideo['type'], info[self.curVideo['type']])
			utilities.notification(utilities.getString(1049), s)

