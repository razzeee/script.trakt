# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import utilities
from utilities import Debug, notification
import copy
import re

progress = xbmcgui.DialogProgress()

class Sync():

	def __init__(self, show_progress=False, run_silent=False, library="all", api=None):
		self.traktapi = api
		self.show_count = 4
		self.show_progress = show_progress
		self.run_silent = run_silent
		self.library = library
		if self.show_progress and self.run_silent:
			Debug("[Sync] Sync is being run silently.")
		self.sync_on_update = utilities.getSettingAsBool('sync_on_update')
		self.notify = utilities.getSettingAsBool('show_sync_notifications')
		self.notify_during_playback = not (xbmc.Player().isPlayingVideo() and utilities.getSettingAsBool("hide_notifications_playback"))
		self.simulate = utilities.getSettingAsBool('simulate_sync')
		if self.simulate:
			Debug("[Sync] Sync is configured to be simulated.")

		_opts = ['ExcludePathOption', 'ExcludePathOption2', 'ExcludePathOption3']
		_vals = ['ExcludePath', 'ExcludePath2', 'ExcludePath3']
		self.exclusions = []
		for i in range(3):
			if utilities.getSettingAsBool(_opts[i]):
				_path = utilities.getSetting(_vals[i])
				if _path != "":
					self.exclusions.append(_path)

	def isCanceled(self):
		if self.show_progress and not self.run_silent and progress.iscanceled():
			Debug("[Sync] Sync was canceled by user.")
			return True
		elif xbmc.abortRequested:
			Debug('XBMC abort requested')
			return True
		else:
			return False

	def updateProgress(self, *args, **kwargs):
		if self.show_progress and not self.run_silent:
			kwargs['percent'] = args[0]
			progress.update(**kwargs)

	def checkExclusion(self, file):
		for _path in self.exclusions:
			if file.find(_path) > -1:
				return True
		return False

	''' begin code for episode sync '''
	def traktLoadShows(self):
		self.updateProgress(10, line1=utilities.getString(1485), line2=utilities.getString(1486))

		Debug('[Episodes Sync] Getting episode collection from trakt.tv')
		library_shows = self.traktapi.getShowLibrary()
		if not isinstance(library_shows, list):
			Debug("[Episodes Sync] Invalid trakt.tv show list, possible error getting data from trakt, aborting trakt.tv collection update.")
			return False

		self.updateProgress(12, line2=utilities.getString(1487))

		Debug('[Episodes Sync] Getting watched episodes from trakt.tv')
		watched_shows = self.traktapi.getWatchedEpisodeLibrary()
		if not isinstance(watched_shows, list):
			Debug("[Episodes Sync] Invalid trakt.tv watched show list, possible error getting data from trakt, aborting trakt.tv watched update.")
			return False

		shows = []
		i = 0
		x = float(len(library_shows))
		# reformat show array
		for show in library_shows:
			
			show['title'] = show['show']['title']
			show['imdb_id'] = show['show']['ids']['imdb']
			show['tvdb_id'] = show['show']['ids']['tvdb']
			show['year'] = show['show']['year']
			
			if show['title'] is None and show['imdb_id'] is None and show['tvdb_id'] is None:
				# has no identifing values, skip it
				continue

			y = {}
			w = {}
			for s in show['seasons']:
				episodes_a = []
				for e in s['episodes']:
					episodes_a.append(e['number'])
				y[s['number']] = episodes_a
				w[s['number']] = []
			show['seasons'] = y
			show['watched'] = w
			show['in_collection'] = True
			if show['imdb_id'] is None:
				show['imdb_id'] = ""
			if show['tvdb_id'] is None:
				show['tvdb_id'] = ""

			shows.append(show)

			i = i + 1
			y = ((i / x) * 8) + 12
			self.updateProgress(int(y), line2=utilities.getString(1488))

		i = 0
		x = float(len(watched_shows))
		for watched_show in watched_shows:
			
			watched_show['title'] = watched_show['show']['title']
			watched_show['imdb_id'] = watched_show['show']['ids']['imdb']
			watched_show['tvdb_id'] = watched_show['show']['ids']['tvdb']
			watched_show['year'] = watched_show['show']['year']
			
			if watched_show['title'] is None and watched_show['imdb_id'] is None and watched_show['tvdb_id'] is None:
				# has no identifing values, skip it
				continue

			if watched_show['imdb_id'] is None:
				watched_show['imdb_id'] = ""
			if watched_show['tvdb_id'] is None:
				watched_show['tvdb_id'] = ""
			show = utilities.findShow(watched_show, shows)
			if show:
				for s in watched_show['seasons']:
					episodes_a = []
					for e in s['episodes']:
						episodes_a.append(e['number'])
					show['watched'][s['number']] = episodes_a
			else:
				y = {}
				w = {}
				for s in watched_show['seasons']:
					episodes_a = []
					for e in s['episodes']:
						episodes_a.append(e['number'])
					w[s['number']] = episodes_a
					y[s['number']] = []
				watched_show['seasons'] = y
				watched_show['watched'] = w
				watched_show['in_collection'] = False
				shows.append(watched_show)

			i = i + 1
			y = ((i / x) * 8) + 20
			self.updateProgress(int(y), line2=utilities.getString(1488))

		self.updateProgress(28, line2=utilities.getString(1489))

		return shows
		
	def sendAddERequest(self, data):
		if self.simulate:
			Debug("[Episodes Sync] %s" % str(data))
		else:
			self.traktapi.addEpisode(data)

	def sendRemoveERequest(self, data):
		if self.simulate:
			Debug("[Episodes Sync] %s" % str(data))
		else:
			self.traktapi.removeEpisode(data)

	def sendUpdateERequest(self, data):
		if self.simulate:
			Debug("[Episodes Sync] %s" % str(data))
		else:
			self.traktapi.updateSeenEpisode(data)
			
	def xbmcLoadShowList(self):
		Debug("[Episodes Sync] Getting show data from XBMC")
		data = utilities.xbmcJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShows', 'params': {'properties': ['title', 'imdbnumber', 'year']}, 'id': 0})
		if not data:
			Debug("[Episodes Sync] xbmc json request was empty.")
			return None
		
		if not 'tvshows' in data:
			Debug('[Episodes Sync] Key "tvshows" not found')
			return None

		shows = data['tvshows']
		Debug("[Episodes Sync] XBMC JSON Result: '%s'" % str(shows))

		# reformat show array
		for show in shows:
			show['in_collection'] = True
			show['tvdb_id'] = ""
			show['imdb_id'] = ""
			id = show['imdbnumber']
			if id.startswith("tt"):
				show['imdb_id'] = id
			if id.isdigit():
				show['tvdb_id'] = id
			del(show['imdbnumber'])
			del(show['label'])
		return shows

	def xbmcLoadShows(self):
		self.updateProgress(1, line1=utilities.getString(1480), line2=utilities.getString(1481))

		tvshows = self.xbmcLoadShowList()
		if tvshows is None:
			return None
			
		self.updateProgress(2, line2=utilities.getString(1482))

		i = 0
		x = float(len(tvshows))
		Debug("[Episodes Sync] Getting episode data from XBMC")
		for show in tvshows:
			show['seasons'] = {}
			show['watched'] = {}
			data = utilities.xbmcJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': show['tvshowid'], 'properties': ['season', 'episode', 'playcount', 'uniqueid', 'file']}, 'id': 0})
			if not data:
				Debug("[Episodes Sync] There was a problem getting episode data for '%s', aborting sync." % show['title'])
				return None
			if not 'episodes' in data:
				Debug("[Episodes Sync] '%s' has no episodes in XBMC." % show['title'])
				continue
			episodes = data['episodes']
			for e in episodes:
				if self.checkExclusion(e['file']):
					continue
				_season = e['season']
				_episode = e['episode']
				if not _season in show['seasons']:
					show['seasons'][_season] = {}
					show['watched'][_season] = []
				if not _episode in show['seasons'][_season]:
					show['seasons'][_season][_episode] = {'id': e['episodeid'], 'episode_tvdb_id': e['uniqueid']['unknown']}
				if e['playcount'] > 0:
					if not _episode in show['watched'][_season]:
						show['watched'][_season].append(_episode)

			i = i + 1
			y = ((i / x) * 8) + 2
			self.updateProgress(int(y), line2=utilities.getString(1483))

		self.updateProgress(10, line2=utilities.getString(1484))

		return tvshows

	def countEpisodes(self, shows, watched=False, collection=True, all=False):
		count = 0
		p = 'watched' if watched else 'seasons'
		for show in shows:
			if all:
				for s in show[p]:
					count += len(show[p][s])
			else:
				if 'in_collection' in show and not show['in_collection'] == collection:
					continue
				for s in show[p]:
					count += len(show[p][s])
		return count
		
	def getShowAsString(self, show, short=False):
		p = []
		if 'seasons' in show:
			for season in show['seasons']:
				s = ""
				if short:
					s = ", ".join(["S%02dE%02d" % (season, i) for i in show['seasons'][season]])
				else:
					episodes = ", ".join([str(i) for i in show['seasons'][season]])
					s = "Season: %d, Episodes: %s" % (season, episodes)
				p.append(s)
		else:
			p = ["All"]
		return "%s [tvdb: %s] - %s" % (show['title'], show['tvdb_id'], ", ".join(p))

	def traktFormatShow(self, show):
		title = show['title']
		title = re.sub(r"\s*\(.*\)","",title)
		show['title'] = title
		data = {'title': show['title'], 'year': show['year'], 'ids': [], 'seasons': []}
		data['ids'].append({'tvdb': show['tvdb_id']})
		if 'imdb_id' in show:
			data['ids']['imdb_id'] = show['imdb_id']
		for season in show['seasons']:
			seasons_a = {'number': season, 'episodes': []}
			for episode in show['seasons'][season]:
				seasons_a['episodes'].append({'number': episode})
			data['seasons'].append(seasons_a)
		return data

	def compareShows(self, shows_col1, shows_col2, watched=False, restrict=False):
		shows = []
		p = 'watched' if watched else 'seasons'
		for show_col1 in shows_col1:
			show_col2 = utilities.findShow(show_col1, shows_col2)
			if show_col2:
				season_diff = {}
				show_col2_seasons = show_col2[p]
				for season in show_col1[p]:
					a = show_col1[p][season]
					if season in show_col2_seasons:
						b = show_col2_seasons[season]
						diff = list(set(a).difference(set(b)))
						if len(diff) > 0:
							if restrict:
								t = list(set(show_col2['seasons'][season]).intersection(set(diff)))
								if len(t) > 0:
									eps = {}
									for ep in t:
										eps[ep] = show_col2['seasons'][season][ep]
									season_diff[season] = eps
							else:
								eps = {}
								for ep in diff:
									eps[ep] = ep
								season_diff[season] = eps
					else:
						if not restrict:
							if len(a) > 0:
								season_diff[season] = a
				if len(season_diff) > 0:
					show = {'title': show_col1['title'], 'tvdb_id': show_col1['tvdb_id'], 'year': show_col1['year'], 'seasons': season_diff}
					if 'imdb_id' in show_col1 and show_col1['imdb_id']:
						show['imdb_id'] = show_col1['imdb_id']
					if 'imdb_id' in show_col2 and show_col2['imdb_id']:
						show['imdb_id'] = show_col2['imdb_id']
					if 'tvshowid' in show_col1:
						show['tvshowid'] = show_col1['tvshowid']
					if 'tvshowid' in show_col2:
						show['tvshowid'] = show_col2['tvshowid']
					shows.append(show)
			else:
				if not restrict:
					if 'in_collection' in show_col1 and show_col1['in_collection']:
						if self.countEpisodes([show_col1], watched=watched) > 0:
							show = {'title': show_col1['title'], 'tvdb_id': show_col1['tvdb_id'], 'year': show_col1['year'], 'seasons': show_col1[p]}
							if 'tvshowid' in show_col1:
								show['tvshowid'] = show_col1['tvshowid']
							shows.append(show)
		return shows

	def traktAddEpisodes(self, shows):
		if len(shows) == 0:
			self.updateProgress(46, line1=utilities.getString(1435), line2=utilities.getString(1490))
			Debug("[Episodes Sync] trakt.tv episode collection is up to date.")
			return

		Debug("[Episodes Sync] %i show(s) have episodes (%d) to be added to your trakt.tv collection." % (len(shows), self.countEpisodes(shows)))
		for show in shows:
			Debug("[Episodes Sync] Episodes added: %s" % self.getShowAsString(show, short=True))
		
		self.updateProgress(28, line1=utilities.getString(1435), line2="%i %s" % (len(shows), utilities.getString(1436)), line3=" ")

		i = 0
		show_no = 0
		x = float(len(shows))
		shows_a = {'shows':[]}
		for show in shows:
			if self.isCanceled():
				return

			epCount = self.countEpisodes([show])
			title = show['title'].encode('utf-8', 'ignore')

			i = i + 1
			y = ((i / x) * 18) + 28
			show_no = show_no + 1
			self.updateProgress(int(y), line1=utilities.getString(1435), line2=title, line3="%i %s" % (epCount, utilities.getString(1437)))

			s = self.traktFormatShow(show)
			shows_a['shows'].append(s)
			if show_no > self.show_count:
				self.sendAddERequest(shows_a)
				show_no = 0
				shows_a = {'shows':[]}
                
		if show_no > 0:
			self.sendAddERequest(shows_a)

		self.updateProgress(46, line1=utilities.getString(1435), line2=utilities.getString(1491) % self.countEpisodes(shows))

	def traktRemoveEpisodes(self, shows):
		if len(shows) == 0:
			self.updateProgress(98, line1=utilities.getString(1445), line2=utilities.getString(1496))
			Debug('[Episodes Sync] trakt.tv episode collection is clean')
			return

		Debug("[Episodes Sync] %i show(s) will have episodes removed from trakt.tv collection." % len(shows))
		for show in shows:
			Debug("[Episodes Sync] Episodes removed: %s" % self.getShowAsString(show, short=True))

		self.updateProgress(82, line1=utilities.getString(1445), line2=utilities.getString(1497) % self.countEpisodes(shows), line3=" ")

		i = 0
		show_no = 0
		x = float(len(shows))
		shows_a = {'shows':[]}
		for show in shows:
			if self.isCanceled():
				return

			epCount = self.countEpisodes([show])
			title = show['title'].encode('utf-8', 'ignore')

			show_no = show_no + 1

			s = self.traktFormatShow(show)
			shows_a['shows'].append(s)
			if show_no > self.show_count:
				self.sendRemoveERequest(shows_a)
				show_no = 0
				shows_a = {'shows':[]}
			i = i + 1
			y = ((i / x) * 16) + 82
			self.updateProgress(int(y), line2=title, line3="%i %s" % (epCount, utilities.getString(1447)))
                
		if show_no > 0:
			self.sendRemoveERequest(shows_a)
		self.updateProgress(98, line2=utilities.getString(1498) % self.countEpisodes(shows), line3=" ")

	def traktUpdateEpisodes(self, shows):
		if len(shows) == 0:
			self.updateProgress(64, line1=utilities.getString(1438), line2=utilities.getString(1492))
			Debug("[Episodes Sync] trakt.tv episode playcounts are up to date.")
			return

		Debug("[Episodes Sync] %i show(s) are missing playcounts on trakt.tv" % len(shows))
		for show in shows:
			Debug("[Episodes Sync] Episodes updated: %s" % self.getShowAsString(show, short=True))

		self.updateProgress(46, line1=utilities.getString(1438), line2="%i %s" % (len(shows), utilities.getString(1439)), line3=" ")

		i = 0
		show_no = 0
		x = float(len(shows))
		shows_a = {'shows':[]}
		for show in shows:
			if self.isCanceled():
				return

			epCount = self.countEpisodes([show])
			title = show['title'].encode('utf-8', 'ignore')

			i = i + 1
			show_no = show_no + 1
			y = ((i / x) * 18) + 46
			self.updateProgress(70, line2=title, line3="%i %s" % (epCount, utilities.getString(1440)))

			s = self.traktFormatShow(show)
			shows_a['shows'].append(s)
			if show_no > self.show_count:
				self.sendUpdateERequest(shows_a)
				show_no = 0
				shows_a = {'shows':[]}
                
		if show_no > 0:
			self.sendUpdateERequest(shows_a)

		self.updateProgress(64, line2="%i %s" % (len(shows), utilities.getString(1439)))

	def xbmcUpdateEpisodes(self, shows):
		if len(shows) == 0:
			self.updateProgress(82, line1=utilities.getString(1441), line2=utilities.getString(1493))
			Debug("[Episodes Sync] XBMC episode playcounts are up to date.")
			return

		Debug("[Episodes Sync] %i show(s) shows are missing playcounts on XBMC" % len(shows))
		for s in ["%s" % self.getShowAsString(s, short=True) for s in shows]:
			Debug("[Episodes Sync] Episodes updated: %s" % s)

		self.updateProgress(64, line1=utilities.getString(1441), line2="%i %s" % (len(shows), utilities.getString(1439)), line3=" ")

		episodes = []
		for show in shows:
			for season in show['seasons']:
				for episode in show['seasons'][season]:
					episodes.append({'episodeid': show['seasons'][season][episode]['id'], 'playcount': 1})

		#split episode list into chunks of 50
		chunked_episodes = utilities.chunks([{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": episodes[i], "id": i} for i in range(len(episodes))], 50)
		i = 0
		x = float(len(chunked_episodes))
		for chunk in chunked_episodes:
			if self.isCanceled():
				return
			if self.simulate:
				Debug("[Episodes Sync] %s" % str(chunk))
			else:
				utilities.xbmcJsonRequest(chunk)

			i = i + 1
			y = ((i / x) * 18) + 64
			self.updateProgress(int(y), line2=utilities.getString(1494))

		self.updateProgress(82, line2=utilities.getString(1495) % len(episodes))

	def syncEpisodes(self):
		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1406)), utilities.getString(1420)) #Sync started
		if self.show_progress and not self.run_silent:
			progress.create("%s %s" % (utilities.getString(1400), utilities.getString(1406)), line1=" ", line2=" ", line3=" ")

		xbmcShows = self.xbmcLoadShows()
		if not isinstance(xbmcShows, list) and not xbmcShows:
			Debug("[Episodes Sync] XBMC show list is empty, aborting tv show Sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		traktShows = self.traktLoadShows()
		if not isinstance(traktShows, list):
			Debug("[Episodes Sync] Error getting trakt.tv show list, aborting tv show sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		if utilities.getSettingAsBool('add_episodes_to_trakt') and not self.isCanceled():
			traktShowsAdd = self.compareShows(xbmcShows, traktShows)
			self.traktAddEpisodes(traktShowsAdd)
		
		if utilities.getSettingAsBool('trakt_episode_playcount') and not self.isCanceled():
			traktShowsUpdate = self.compareShows(xbmcShows, traktShows, watched=True)
			self.traktUpdateEpisodes(traktShowsUpdate)

		if utilities.getSettingAsBool('xbmc_episode_playcount') and not self.isCanceled():
			xbmcShowsUpadate = self.compareShows(traktShows, xbmcShows, watched=True, restrict=True)
			self.xbmcUpdateEpisodes(xbmcShowsUpadate)

		if utilities.getSettingAsBool('clean_trakt_episodes') and not self.isCanceled():
			traktShowsRemove = self.compareShows(traktShows, xbmcShows)
			self.traktRemoveEpisodes(traktShowsRemove)

		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1406)), utilities.getString(1421)) #Sync complete

		if not self.isCanceled() and self.show_progress and not self.run_silent:
			self.updateProgress(100, line1=" ", line2=utilities.getString(1442), line3=" ")
			progress.close()

		Debug("[Episodes Sync] Shows on trakt.tv (%d), shows in XBMC (%d)." % (len(utilities.findAllInList(traktShows, 'in_collection', True)), len(xbmcShows)))
		Debug("[Episodes Sync] Episodes on trakt.tv (%d), episodes in XBMC (%d)." % (self.countEpisodes(traktShows), self.countEpisodes(xbmcShows)))
		Debug("[Episodes Sync] Complete.")

	''' begin code for movie sync '''
	def traktLoadMovies(self):
		self.updateProgress(5, line2=utilities.getString(1462))

		Debug("[Movies Sync] Getting movie collection from trakt.tv")
		movies = self.traktapi.getMovieLibrary()
		if not isinstance(movies, list):
			Debug("[Movies Sync] Invalid trakt.tv movie list, possible error getting data from trakt, aborting trakt.tv collection update.")
			return False

		self.updateProgress(6, line2=utilities.getString(1463))

		Debug("[Movies Sync] Getting seen movies from trakt.tv")
		watched_movies = self.traktapi.getWatchedMovieLibrary()
		if not isinstance(watched_movies, list):
			Debug("[Movies Sync] Invalid trakt.tv movie seen list, possible error getting data from trakt, aborting trakt.tv watched update.")
			return False

		self.updateProgress(8, line2=utilities.getString(1464))

		i = 0
		x = float(len(movies))
		# reformat movie arrays
		for movie in movies:
			movie['plays'] = 0
			movie['in_collection'] = True
			if movie['imdb_id'] is None:
				movie['imdb_id'] = ""
			if movie['tmdb_id'] is None:
				movie['tmdb_id'] = ""

			i = i + 1
			y = ((i / x) * 6) + 8
			self.updateProgress(int(y), line2=utilities.getString(1465))

		i = 0
		x = float(len(watched_movies))
		for movie in watched_movies:
			if movie['imdb_id'] is None:
				movie['imdb_id'] = ""
			if movie['tmdb_id'] is None:
				movie['tmdb_id'] = "" 
			else:
				movie['tmdb_id'] = unicode(movie['tmdb_id'])
			m = utilities.findMovie(movie, movies)
			if m:
				m['plays'] = movie['plays']
			else:
				movie['in_collection'] = False
				movies.append(movie)

			i = i + 1
			y = ((i / x) * 6) + 14
			self.updateProgress(int(y), line2=utilities.getString(1465))

		self.updateProgress(20, line2=utilities.getString(1466))

		return movies

	def xbmcLoadMovies(self):
		self.updateProgress(1, line2=utilities.getString(1460))

		Debug("[Movies Sync] Getting movie data from XBMC")
		data = utilities.xbmcJsonRequest({'jsonrpc': '2.0', 'id': 0, 'method': 'VideoLibrary.GetMovies', 'params': {'properties': ['title', 'imdbnumber', 'year', 'playcount', 'lastplayed', 'file']}})
		if not data:
			Debug("[Movies Sync] XBMC JSON request was empty.")
			return
		
		if not 'movies' in data:
			Debug('[Movies Sync] Key "movies" not found')
			return

		movies = data['movies']
		Debug("[Movies Sync] XBMC JSON Result: '%s'" % str(movies))

		i = 0
		x = float(len(movies))
		
		xbmc_movies = []

		# reformat movie array
		for movie in movies:
			if self.checkExclusion(movie['file']):
				continue
			if movie['lastplayed']:
				movie['last_played'] = utilities.sqlDateToUnixDate(movie['lastplayed'])
			movie['plays'] = movie.pop('playcount')
			movie['in_collection'] = True
			movie['imdb_id'] = ""
			movie['tmdb_id'] = ""
			id = movie['imdbnumber']
			if id.startswith("tt"):
				movie['imdb_id'] = id
			if id.isdigit():
				movie['tmdb_id'] = id
			del(movie['imdbnumber'])
			del(movie['lastplayed'])
			del(movie['label'])
			del(movie['file'])

			xbmc_movies.append(movie)

			i = i + 1
			y = ((i / x) * 4) + 1
			self.updateProgress(int(y))
			
		self.updateProgress(5, line2=utilities.getString(1461))

		return xbmc_movies

	def sanitizeMovieData(self, movie):
		data = copy.deepcopy(movie)
		if 'in_collection' in data:
			del(data['in_collection'])
		if 'movieid' in data:
			del(data['movieid'])
		if not data['tmdb_id']:
			del(data['tmdb_id'])
		return data

	def countMovies(self, movies, collection=True):
		if len(movies) > 0:
			if 'in_collection' in movies[0]:
				return len(utilities.findAllInList(movies, 'in_collection', collection))
			else:
				return len(movies)
		return 0

	def compareMovies(self, movies_col1, movies_col2, watched=False, restrict=False):
		movies = []
		for movie_col1 in movies_col1:
			movie_col2 = utilities.findMovie(movie_col1, movies_col2)
			if movie_col2:
				if watched:
					if (movie_col2['plays'] == 0) and (movie_col1['plays'] > movie_col2['plays']):
						if 'movieid' not in movie_col1:
							movie_col1['movieid'] = movie_col2['movieid']
						movies.append(movie_col1)
				else:
					if 'in_collection' in movie_col2 and not movie_col2['in_collection']:
						movies.append(movie_col1)
			else:
				if not restrict:
					if 'in_collection' in movie_col1 and movie_col1['in_collection']:
						if watched and (movie_col1['plays'] > 0):
							movies.append(movie_col1)
						elif not watched:
							movies.append(movie_col1)
		return movies

	def traktAddMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(40, line2=utilities.getString(1467))
			Debug("[Movies Sync] trakt.tv movie collection is up to date.")
			return
		
		titles = ", ".join(["%s (%s)" % (m['title'], m['imdb_id']) for m in movies])
		Debug("[Movies Sync] %i movie(s) will be added to trakt.tv collection." % len(movies))
		Debug("[Movies Sync] Movies added: %s" % titles)

		self.updateProgress(20, line2="%i %s" % (len(movies), utilities.getString(1426)))

		chunked_movies = utilities.chunks([self.sanitizeMovieData(movie) for movie in movies], 50)
		i = 0
		x = float(len(chunked_movies))
		for chunk in chunked_movies:
			if self.isCanceled():
				return
			params = {'movies': chunk}
			if self.simulate:
				Debug("[Movies Sync] %s" % str(params))
			else:
				self.traktapi.addMovie(params)

			i = i + 1
			y = ((i / x) * 20) + 20
			self.updateProgress(int(y), line2=utilities.getString(1477))

		self.updateProgress(40, line2=utilities.getString(1468) % len(movies))

	def traktRemoveMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(98, line2=utilities.getString(1474))
			Debug("[Movies Sync] trakt.tv movie collection is clean, no movies to remove.")
			return
		
		titles = ", ".join(["%s (%s)" % (m['title'], m['imdb_id']) for m in movies])
		Debug("[Movies Sync] %i movie(s) will be removed from trakt.tv collection." % len(movies))
		Debug("[Movies Sync] Movies removed: %s" % titles)

		self.updateProgress(80, line2="%i %s" % (len(movies), utilities.getString(1444)))
		
		chunked_movies = utilities.chunks([self.sanitizeMovieData(movie) for movie in movies], 50)
		i = 0
		x = float(len(chunked_movies))
		for chunk in chunked_movies:
			if self.isCanceled():
				return
			params = {'movies': chunk}
			if self.simulate:
				Debug("[Movies Sync] %s" % str(params))
			else:
				self.traktapi.removeMovie(params)

			i = i + 1
			y = ((i / x) * 20) + 80
			self.updateProgress(int(y), line2=utilities.getString(1476))

		self.updateProgress(98, line2=utilities.getString(1475) % len(movies))

	def traktUpdateMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(60, line2=utilities.getString(1469))
			Debug("[Movies Sync] trakt.tv movie playcount is up to date")
			return
		
		titles = ", ".join(["%s (%s)" % (m['title'], m['imdb_id']) for m in movies])
		Debug("[Movies Sync] %i movie(s) playcount will be updated on trakt.tv" % len(movies))
		Debug("[Movies Sync] Movies updated: %s" % titles)

		self.updateProgress(40, line2="%i %s" % (len(movies), utilities.getString(1428)))

		# Send request to update playcounts on trakt.tv
		chunked_movies = utilities.chunks([self.sanitizeMovieData(movie) for movie in movies], 50)
		i = 0
		x = float(len(chunked_movies))
		for chunk in chunked_movies:
			if self.isCanceled():
				return
			params = {'movies': chunk}
			if self.simulate:
				Debug("[Movies Sync] %s" % str(params))
			else:
				self.traktapi.updateSeenMovie(params)

			i = i + 1
			y = ((i / x) * 20) + 40
			self.updateProgress(int(y), line2=utilities.getString(1478))

		self.updateProgress(60, line2=utilities.getString(1470) % len(movies))

	def xbmcUpdateMovies(self, movies):
		if len(movies) == 0:
			self.updateProgress(80, line2=utilities.getString(1471))
			Debug("[Movies Sync] XBMC movie playcount is up to date.")
			return
		
		titles = ", ".join(["%s (%s)" % (m['title'], m['imdb_id']) for m in movies])
		Debug("[Movies Sync] %i movie(s) playcount will be updated in XBMC" % len(movies))
		Debug("[Movies Sync] Movies updated: %s" % titles)

		self.updateProgress(60, line2="%i %s" % (len(movies), utilities.getString(1430)))

		#split movie list into chunks of 50
		chunked_movies = utilities.chunks([{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": movies[i]['movieid'], "playcount": movies[i]['plays']}, "id": i} for i in range(len(movies))], 50)
		i = 0
		x = float(len(chunked_movies))
		for chunk in chunked_movies:
			if self.isCanceled():
				return
			if self.simulate:
				Debug("[Movies Sync] %s" % str(chunk))
			else:
				utilities.xbmcJsonRequest(chunk)

			i = i + 1
			y = ((i / x) * 20) + 60
			self.updateProgress(int(y), line2=utilities.getString(1472))

		self.updateProgress(80, line2=utilities.getString(1473) % len(movies))

	def syncMovies(self):
		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1402)), utilities.getString(1420)) #Sync started
		if self.show_progress and not self.run_silent:
			progress.create("%s %s" % (utilities.getString(1400), utilities.getString(1402)), line1=" ", line2=" ", line3=" ")

		xbmcMovies = self.xbmcLoadMovies()
		if not isinstance(xbmcMovies, list) and not xbmcMovies:
			Debug("[Movies Sync] XBMC movie list is empty, aborting movie Sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		traktMovies = self.traktLoadMovies()
		if not isinstance(traktMovies, list):
			Debug("[Movies Sync] Error getting trakt.tv movie list, aborting movie Sync.")
			if self.show_progress and not self.run_silent:
				progress.close()
			return

		if utilities.getSettingAsBool('add_movies_to_trakt') and not self.isCanceled():
			traktMoviesToAdd = self.compareMovies(xbmcMovies, traktMovies)
			self.traktAddMovies(traktMoviesToAdd)
		
		if utilities.getSettingAsBool('trakt_movie_playcount') and not self.isCanceled():
			traktMoviesToUpdate = self.compareMovies(xbmcMovies, traktMovies, watched=True)
			self.traktUpdateMovies(traktMoviesToUpdate)

		if utilities.getSettingAsBool('xbmc_movie_playcount') and not self.isCanceled():
			xbmcMoviesToUpdate = self.compareMovies(traktMovies, xbmcMovies, watched=True, restrict=True)
			self.xbmcUpdateMovies(xbmcMoviesToUpdate)

		if utilities.getSettingAsBool('clean_trakt_movies') and not self.isCanceled():
			traktMoviesToRemove = self.compareMovies(traktMovies, xbmcMovies)
			self.traktRemoveMovies(traktMoviesToRemove)

		if not self.isCanceled() and self.show_progress and not self.run_silent:
			self.updateProgress(100, line1=utilities.getString(1431), line2=" ", line3=" ")
			progress.close()

		if not self.show_progress and self.sync_on_update and self.notify and self.notify_during_playback:
			notification('%s %s' % (utilities.getString(1400), utilities.getString(1402)), utilities.getString(1421)) #Sync complete
		
		Debug("[Movies Sync] Movies on trakt.tv (%d), movies in XBMC (%d)." % (len(traktMovies), self.countMovies(xbmcMovies)))
		Debug("[Movies Sync] Complete.")

	def syncCheck(self, media_type):
		if media_type == 'movies':
			return utilities.getSettingAsBool('add_movies_to_trakt') or utilities.getSettingAsBool('trakt_movie_playcount') or utilities.getSettingAsBool('xbmc_movie_playcount') or utilities.getSettingAsBool('clean_trakt_movies')
		else:
			return utilities.getSettingAsBool('add_episodes_to_trakt') or utilities.getSettingAsBool('trakt_episode_playcount') or utilities.getSettingAsBool('xbmc_episode_playcount') or utilities.getSettingAsBool('clean_trakt_episodes')

		return False

	def sync(self):
		Debug("[Sync] Starting synchronization with trakt.tv")

		if self.syncCheck('movies'):
			if self.library in ["all", "movies"]:
				self.syncMovies()
			else:
				Debug("[Sync] Movie sync is being skipped for this manual sync.")
		else:
			Debug("[Sync] Movie sync is disabled, skipping.")

		if self.syncCheck('episodes'):
			if self.library in ["all", "episodes"]:
				self.syncEpisodes()
			else:
				Debug("[Sync] Episode sync is being skipped for this manual sync.")
		else:
			Debug("[Sync] Episode sync is disabled, skipping.")

		Debug("[Sync] Finished synchronization with trakt.tv")
	
