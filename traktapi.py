# -*- coding: utf-8 -*-
#

import xbmc
import xbmcaddon
import xbmcgui
import time, socket
import math
import urllib2
import base64

from utilities import Debug, notification, getSetting, getSettingAsBool, getSettingAsInt, getString, setSetting
from urllib2 import Request, urlopen, HTTPError, URLError
from httplib import HTTPException, BadStatusLine

try:
	import simplejson as json
except ImportError:
	import json

try:
	from hashlib import sha1
except ImportError:
	from sha import new as sha1

# read settings
__addon__ = xbmcaddon.Addon('script.trakt')
__addonversion__ = __addon__.getAddonInfo('version')

class traktError(Exception):
	def __init__(self, value, code=None):
		self.value = value
		if code:
			self.code = code
	def __str__(self):
		return repr(self.value)

class traktAuthProblem(traktError): pass
class traktServerBusy(traktError): pass
class traktUnknownError(traktError): pass
class traktNotFoundError(traktError): pass
class traktNetworkError(traktError):
	def __init__(self, value, timeout):
		super(traktNetworkError, self).__init__(value)
		self.timeout = timeout

class traktAPI(object):

	__apikey = "d4161a7a106424551add171e5470112e4afdaf2438e6ef2fe0548edc75924868"
	__baseURL = "https://api.trakt.tv"
	__username = ""
	__password = ""
	__userToken = ""
	__apiVersion = "2"

	def __init__(self, loadSettings=False):
		Debug("[traktAPI] Initializing.")

		self.__username = getSetting('username')
		self.__password = getSetting('password')

		self.settings = None
		if loadSettings:
			self.getAccountSettings()

		self.__userToken = self.__userLogin()

	def __userLogin(self):
		# inject username/pass into json data
		args = {}
		args['login'] = self.__username
		args['password'] = self.__password

		# convert to json data
		jdata = json.dumps(args)

		url = "%s/auth/login" % (self.__baseURL)
		# Login
		data = self.traktRequest("POST",url,args)

		Debug("[traktAPI] __userLogin(): token: '%s'" % data['token'])
		return data['token']


	def __getData(self, url, args, timeout=60):
		data = None
		try:
			Debug("[traktAPI] __getData(): urllib2.Request(%s)" % url)

			if args is None or args == {} :
				Debug("[traktAPI] __getData(): Without args")
				req = Request(url)
			else:
				Debug("[traktAPI] __getData(): With args")
				req = Request(url, args)
			
			req.add_header('trakt-user-login', self.__username);
			req.add_header('trakt-user-token', self.__userToken);
			req.add_header('Content-type', 'application/json');
			req.add_header('trakt-api-key', self.__apikey);
			req.add_header('trakt-api-version', '2');
			
			Debug("[traktAPI] __getData(): urllib2.urlopen()")
			t1 = time.time()
			response = urlopen(req, timeout=timeout)
			t2 = time.time()

			Debug("[traktAPI] __getData(): response.read()")
			data = response.read()

			Debug("[traktAPI] __getData(): Response Code: %i" % response.getcode())
			Debug("[traktAPI] __getData(): Response Time: %0.2f ms" % ((t2 - t1) * 1000))
			Debug("[traktAPI] __getData(): Response Headers: %s" % str(response.info().dict))

		except BadStatusLine, e:
			raise traktUnknownError("BadStatusLine: '%s' from URL: '%s'" % (e.line, url))
		except IOError, e:
			if hasattr(e, 'code'): # error 401 or 503, possibly others
				# read the error document, strip newlines, this will make an html page 1 line
				error_data = e.read().replace("\n", "").replace("\r", "")

				if e.code == 401: # authentication problem
					raise traktAuthProblem(error_data)
				elif e.code == 503: # server busy problem
					raise traktServerBusy(error_data)
				else:
					try:
						_data = json.loads(error_data)
						if 'status' in _data:
							data = error_data
					except ValueError:
						raise traktUnknownError(error_data, e.code)

			elif hasattr(e, 'reason'): # usually a read timeout, or unable to reach host
				raise traktNetworkError(str(e.reason), isinstance(e.reason, socket.timeout))

			else:
				raise traktUnknownError(e.message)

		return data

	# make a JSON api request to trakt
	# method: http method (GET or POST)
	# req: REST request (ie '/users/library/movies/all.json/%%API_KEY%%/%%USERNAME%%')
	# args: arguments to be passed by POST JSON (only applicable to POST requests), default:{}
	# returnStatus: when unset or set to false the function returns None upon error and shows a notification,
	#	when set to true the function returns the status and errors in ['error'] as given to it and doesn't show the notification,
	#	use to customise error notifications
	# silent: default is True, when true it disable any error notifications (but not debug messages)
	# hideResponse: used to not output the json response to the log
	def traktRequest(self, method, url, args=None, returnStatus=False, returnOnFailure=False, silent=True, hideResponse=False):
		raw = None
		data = None
		jdata = {}
		retries = getSettingAsInt('retries')

		if args is None:
			args = {}

		if not (method == 'POST' or method == 'GET'):
			Debug("[traktAPI] traktRequest(): Unknown method '%s'." % method)
			return None

		if method == 'POST':
			# debug log before username and sha1hash are injected
			Debug("[traktAPI] traktRequest(): Request data: '%s'." % str(json.dumps(args)))

			# convert to json data
			jdata = json.dumps(args)

		Debug("[traktAPI] traktRequest(): Starting retry loop, maximum %i retries." % retries)

		# start retry loop
		for i in range(retries):
			Debug("[traktAPI] traktRequest(): (%i) Request URL '%s'" % (i, url))

			# check if we are closing
			if xbmc.abortRequested:
				Debug("[traktAPI] traktRequest(): (%i) xbmc.abortRequested" % i)
				break

			try:
				# get data from trakt.tv
				raw = self.__getData(url, jdata)
			except traktError, e:
				if isinstance(e, traktServerBusy):
					Debug("[traktAPI] traktRequest(): (%i) Server Busy (%s)" % (i, e.value))
					xbmc.sleep(5000)
				elif isinstance(e, traktAuthProblem):
					Debug("[traktAPI] traktRequest(): (%i) Authentication Failure (%s)" % (i, e.value))
					setSetting('account_valid', False)
					notification('trakt', getString(1110))
					return
				elif isinstance(e, traktNetworkError):
					Debug("[traktAPI] traktRequest(): (%i) Network error: %s" % (i, e.value))
					if e.timeout:
						notification('trakt', getString(1108) + " (timeout)") # can't connect to trakt
					xbmc.sleep(5000)
				elif isinstance(e, traktUnknownError):
					Debug("[traktAPI] traktRequest(): (%i) Other problem (%s)" % (i, e.value))
					xbmc.sleep(5000)
				else:
					pass

				xbmc.sleep(1000)
				continue

			# check if we are closing
			if xbmc.abortRequested:
				Debug("[traktAPI] traktRequest(): (%i) xbmc.abortRequested" % i)
				break

			# check that returned data is not empty
			if not raw:
				Debug("[traktAPI] traktRequest(): (%i) JSON Response empty" % i)
				xbmc.sleep(1000)
				continue

			try:
				# get json formatted data
				data = json.loads(raw)
				if hideResponse:
					Debug("[traktAPI] traktRequest(): (%i) JSON response recieved, response not logged" % i)
				else:
					Debug("[traktAPI] traktRequest(): (%i) JSON response: '%s'" % (i, str(data)))
			except ValueError:
				# malformed json response
				Debug("[traktAPI] traktRequest(): (%i) Bad JSON response: '%s'" % (i, raw))
				if not silent:
					notification('trakt', getString(1109) + ": Bad response from trakt") # Error

			# check for the status variable in JSON data
			if data and 'status' in data:
				if data['status'] == 'success':
					break
				elif returnOnFailure and data['status'] == 'failure':
					Debug("[traktAPI] traktRequest(): Return on error set, breaking retry.")
					break
				elif 'error' in data and data['status'] == 'failure':
					Debug("[traktAPI] traktRequest(): (%i) JSON Error '%s' -> '%s'" % (i, data['status'], data['error']))
					xbmc.sleep(1000)
					continue
				else:
					pass

			# check to see if we have data, an empty array is still valid data, so check for None only
			if not data is None:
				Debug("[traktAPI] traktRequest(): Have JSON data, breaking retry.")
				break

			xbmc.sleep(500)

		# handle scenario where all retries fail
		if data is None:
			Debug("[traktAPI] traktRequest(): JSON Request failed, data is still empty after retries.")
			return None

		if 'status' in data:
			if data['status'] == 'failure':
				Debug("[traktAPI] traktRequest(): Error: %s" % str(data['error']))
				if returnStatus or returnOnFailure:
					return data
				if not silent:
					notification('trakt', getString(1109) + ": " + str(data['error'])) # Error
				return None
			elif data['status'] == 'success':
				Debug("[traktAPI] traktRequest(): JSON request was successful.")

		return data

	# helper for onSettingsChanged
	def updateSettings(self):

		_username = getSetting('username')
		_password = getSetting('password')

		if not ((self.__username == _username)):
			self.__username = _username

		if not ((self.__password == _password)):
			self.__password = _password			


	# url: http://api.trakt.tv/account/settings/<apikey>
	# returns: all settings for authenticated user
	def getAccountSettings(self, force=False):
		_interval = (60 * 60 * 24 * 7) - (60 * 60) # one week less one hour

		_next = getSettingAsInt('trakt_settings_last') + _interval
		stale = force

		if force:
			Debug("[traktAPI] Forcing a reload of settings from trakt.tv.")

		if not stale and time.time() >= _next:
			Debug("[traktAPI] trakt.tv account settings are stale, reloading.")
			stale = True

		if stale:
				Debug("[traktAPI] Getting account settings for '%s'." % self.__username)
				url = "%s/account/settings/%s" % (self.__baseURL, self.__apikey)
				Debug("[traktAPI] getAccountSettings(url: %s)" % url)
				response = self.traktRequest('POST', url, hideResponse=True)
				if response and 'status' in response:
					if response['status'] == 'success':
						del response['status']
						setSetting('trakt_settings', json.dumps(response))
						setSetting('trakt_settings_last', int(time.time()))
						self.settings = response

		else:
			Debug("[traktAPI] Loaded cached account settings for '%s'." % self.__username)
			s = getSetting('trakt_settings')
			self.settings = json.loads(s)

	# helper to get rating mode, returns the setting from trakt.tv, or 'advanced' if there were problems getting them
	def getRatingMode(self):
		if not self.settings:
			self.getAccountSettings()
		rating_mode = "advanced"
		if self.settings and 'viewing' in self.settings:
			rating_mode = self.settings['viewing']['ratings']['mode']
		return rating_mode


	# url: http://api.trakt.tv/<show|movie>/scrobble/<apikey>
	# returns: {"status": "success","message": "scrobbled The Walking Dead 1x01"}
	def scrobble(self, data, status):
			url = "%s/scrobble/%s" % (self.__baseURL, status)
			Debug("[traktAPI] scrobble(url: %s, data: %s)" % (url, str(data)))
			if getSettingAsBool('simulate_scrobbling'):
				Debug("[traktAPI] Simulating response.")
				return {'status': 'success'}
			else:
				return self.traktRequest('POST', url, data, returnOnFailure=True)

	def scrobbleEpisode(self, info, percent, status):
		data = { 'show': {'title': info['showtitle'], 'year': info['year']}, 'episode': { 'season': info['season'], 'number': info['episode']}, 'progress': math.ceil(percent)}
		if 'uniqueid' in info:
			data['episode_tvdb_id'] = info['uniqueid']['unknown']
		return self.scrobble(data, status)
	def scrobbleMovie(self, info, percent, status):
		data = { 'movie': { 'ids': {'imdb': info['imdbnumber']}, 'title': info['title'], 'year': info['year']}, 'progress': math.ceil(percent)}
		return self.scrobble(data, status)

	# url: http://api.trakt.tv/users/<username>/collection/<shows|movies>
	# response: [{u'last_collected_at': u'2014-12-03T22:01:57.000-08:00', u'seasons': [{u'episodes': [{u'number': 1, u'collected_at': u'2014-12-03T22:01:57.000-08:00'}, {u'number': 2, u'collected_at': u'2014-12-03T22:01:57.000-08:00'}, {u'number': 3, u'collected_at': u'2014-12-03T22:01:57.000-08:00'}, {u'number': 4, u'collected_at': u'2014-12-03T22:01:57.000-08:00'}, {u'number': 5, u'collected_at': u'2014-12-03T22:01:57.000-08:00'}], u'number': 1}], u'show': {u'year': 2012, u'ids': {u'tmdb': None, u'tvdb': 258519, u'trakt': 66328, u'imdb': u'tt2007042', u'tvrage': None, u'slug': u'whale-wars-viking-shores'}, u'title': u'Whale Wars: Viking Shores'}}]
	# note: if user has nothing in collection, response is then []
	def getLibrary(self, type):
			url = "%s/sync/collection/%s" % (self.__baseURL, type)
			Debug("[traktAPI] getLibrary(url: %s)" % url)
			return self.traktRequest('GET', url)

	def getShowLibrary(self):
		return self.getLibrary('shows')
	def getMovieLibrary(self):
		return self.getLibrary('movies')

	# url: http://api.trakt.tv/users/<username>/watched/<shows|movies>
	# returns: [{u'seasons': [{u'episodes': [{u'plays': 14, u'number': 1}, {u'plays': 14, u'number': 2}, {u'plays': 14, u'number': 3}, {u'plays': 14, u'number': 4}, {u'plays': 14, u'number': 5}], u'number': 1}], u'last_watched_at': u'2015-01-15T22:30:39.000-08:00', u'plays': 70, u'show': {u'year': 2012, u'ids': {u'tmdb': None, u'tvdb': 258519, u'trakt': 66328, u'imdb': u'tt2007042', u'tvrage': None, u'slug': u'whale-wars-viking-shores'}, u'title': u'Whale Wars: Viking Shores'}}]
	# note: if nothing watched in collection, returns []
	def getWatchedLibrary(self, type):
			url = "%s/sync/watched/%s" % (self.__baseURL, type)
			Debug("[traktAPI] getWatchedLibrary(url: %s)" % url)
			return self.traktRequest('GET', url)

	def getWatchedEpisodeLibrary(self,):
		return self.getWatchedLibrary('shows')
	def getWatchedMovieLibrary(self):
		return self.getWatchedLibrary('movies')

	# url: http://api.trakt.tv/sync/collection>
	# returns: {'added': {'movies': 1,'episodes': 12},'updated': {'movies': 0,'episodes': 0},'existing': {'movies': 0,'episodes': 0},'not_found': {'movies': [{'ids': {'imdb': 'tt0000111'}}],'shows': [],'seasons': [],'episodes': []}}
	def addToLibrary(self, type, data):
			url = "%s/sync/collection" % (self.__baseURL)
			Debug("[traktAPI] addToLibrary(url: %s, data: %s)" % (url, str(data)))
			return self.traktRequest('POST', url, data)

	def addEpisode(self, data):
		return self.addToLibrary('show/episode', data)
	def addShow(self, data):
		return self.addToLibrary('show', data)
	def addMovie(self, data):
		return self.addToLibrary('movie', data)

	# url: http://api.trakt.tv/<show|show/episode|movie>/unlibrary/<apikey>
	# returns:
	def removeFromLibrary(self, type, data):
			url = "%s/%s/unlibrary/%s" % (self.__baseURL, type, self.__apikey)
			Debug("[traktAPI] removeFromLibrary(url: %s, data: %s)" % (url, str(data)))
			return self.traktRequest('POST', url, data)

	def removeEpisode(self, data):
		return self.removeFromLibrary('show/episode', data)
	def removeShow(self, data):
		return self.removeFromLibrary('show', data)
	def removeMovie(self, data):
		return self.removeFromLibrary('movie', data)

	# url: http://api.trakt.tv/sync/history
	# returns: {'added': {'movies': 1,'episodes': 12},'updated': {'movies': 0,'episodes': 0},'existing': {'movies': 0,'episodes': 0},'not_found': {'movies': [{'ids': {'imdb': 'tt0000111'}}],'shows': [],'seasons': [],'episodes': []}}
	def updateSeenInLibrary(self, type, data):
			url = "%s/sync/history" % (self.__baseURL)
			Debug("[traktAPI] updateSeenInLibrary(url: %s, data: %s)" % (url, str(data)))
			return self.traktRequest('POST', url, data)

	def updateSeenEpisode(self, data):
		return self.updateSeenInLibrary('show/episode', data)
	def updateSeenShow(self, data):
		return self.updateSeenInLibrary('show', data)
	def updateSeenMovie(self, data):
		return self.updateSeenInLibrary('movie', data)

	# url: http://api.trakt.tv/<show|show/episode|movie>/summary.format/apikey/title[/season/episode]
	# returns: returns information for a movie, show or episode
	def getSummary(self, type, data):
			url = "%s/%s/summary.json/%s/%s" % (self.__baseURL, type, self.__apikey, data)
			Debug("[traktAPI] getSummary(url: %s)" % url)
			return self.traktRequest('POST', url)

	def getShowSummary(self, id, extended=False):
		data = str(id)
		if extended:
			data = "%s/extended" % data
		return self.getSummary('show', data)
	def getEpisodeSummary(self, id, season, episode):
		data = "%s/%s/%s" % (id, season, episode)
		return self.getSummary('show/episode', data)
	def getMovieSummary(self, id):
		data = str(id)
		return self.getSummary('movie', data)

	# url: http://api.trakt.tv/show/season.format/apikey/title/season
	# returns: returns detailed episode info for a specific season of a show.
	def getSeasonInfo(self, id, season):
			url = "%s/show/season.json/%s/%s/%d" % (self.__baseURL, self.__apikey, id, season)
			Debug("[traktAPI] getSeasonInfo(url: %s)" % url)
			return self.traktRequest('POST', url)

	# url: http://api.trakt.tv/sync/ratings
	# returns: {"status":"success","message":"rated Portlandia 1x01","type":"episode","rating":"love","ratings":{"percentage":100,"votes":2,"loved":2,"hated":0},"facebook":true,"twitter":true,"tumblr":false}
	def rate(self, type, data):

			url = "%s/sync/ratings" % (self.__baseURL)
			Debug("[traktAPI] rate(url: %s, data: %s)" % (url, str(data)))
			return self.traktRequest('POST', url, data)

	def rateShow(self, data):
		return self.rate('shows', data)
	def rateEpisode(self, data):
		return self.rate('episodes', data)
	def rateMovie(self, data):
		return self.rate('movies', data)

	# url: http://api.trakt.tv/users/lists.json/apikey/<username>
	# returns: Returns all custom lists for a user.
	def getUserLists(self):
			url = "%s/users/lists.json/%s/%s" % (self.__baseURL, self.__apikey, self.__username)
			Debug("[traktAPI] getUserLists(url: %s)" % url)
			return self.traktRequest('POST', url)

	# url: http://api.trakt.tv/users/list.json/apikey/<username>/<slug>
	# returns: Returns list details and all items it contains.
	def getUserList(self, data):
			url = "%s/users/list.json/%s/%s/%s" % (self.__baseURL, self.__apikey, self.__username, data)
			Debug("[traktAPI] getUserList(url: %s)" % url)
			return self.traktRequest('POST', url)

	# url: http://api.trakt.tv/lists/<add|delete|items/add|items/delete>/apikey
	# returns: {"status": "success","message": ... }
	# note: return data varies based on method, but all include status/message
	def userList(self, method, data):
			url = "%s/lists/%s/%s" % (self.__baseURL, method, self.__apikey)
			Debug("[traktAPI] userList(url: %s, data: %s)" % (url, str(data)))
			return self.traktRequest('POST', url, data)

	def userListAdd(self, list_name, privacy, description=None, allow_shouts=False, show_numbers=False):
		data = {'name': list_name, 'show_numbers': show_numbers, 'allow_shouts': allow_shouts, 'privacy': privacy}
		if description:
			data['description'] = description
		return self.userList('add', data)
	def userListDelete(self, slug_name):
		data = {'slug': slug_name}
		return self.userList('delete', data)
	def userListItemAdd(self, data):
		return self.userList('items/add', data)
	def userListItemDelete(self, data):
		return self.userList('items/delete', data)
	def userListUpdate(self, data):
		return self.userList('update', data)

	# url: http://api.trakt.tv/users/watchlist/<movies|shows>.json/<apikey>/<username>
	# returns: [{"title":"GasLand","year":2010,"released":1264320000,"url":"http://trakt.tv/movie/gasland-2010","runtime":107,"tagline":"Can you light your water on fire? ","overview":"It is happening all across America-rural landowners wake up one day to find a lucrative offer from an energy company wanting to lease their property. Reason? The company hopes to tap into a reservoir dubbed the \"Saudi Arabia of natural gas.\" Halliburton developed a way to get the gas out of the ground-a hydraulic drilling process called \"fracking\"-and suddenly America finds itself on the precipice of becoming an energy superpower.","certification":"","imdb_id":"tt1558250","tmdb_id":"40663","inserted":1301130302,"images":{"poster":"http://trakt.us/images/posters_movies/1683.jpg","fanart":"http://trakt.us/images/fanart_movies/1683.jpg"},"genres":["Action","Comedy"]},{"title":"The King's Speech","year":2010,"released":1291968000,"url":"http://trakt.tv/movie/the-kings-speech-2010","runtime":118,"tagline":"God save the king.","overview":"Tells the story of the man who became King George VI, the father of Queen Elizabeth II. After his brother abdicates, George ('Bertie') reluctantly assumes the throne. Plagued by a dreaded stutter and considered unfit to be king, Bertie engages the help of an unorthodox speech therapist named Lionel Logue. Through a set of unexpected techniques, and as a result of an unlikely friendship, Bertie is able to find his voice and boldly lead the country into war.","certification":"R","imdb_id":"tt1504320","tmdb_id":"45269","inserted":1301130174,"images":{"poster":"http://trakt.us/images/posters_movies/8096.jpg","fanart":"http://trakt.us/images/fanart_movies/8096.jpg"},"genres":["Action","Comedy"]}]
	# note: if nothing in list, returns []
	def getWatchlist(self, type):
			url = "%s/users/watchlist/%s.json/%s/%s" % (self.__baseURL, type, self.__apikey, self.__username)
			Debug("[traktAPI] getWatchlist(url: %s)" % url)
			return self.traktRequest('POST', url)

	def getWatchlistShows(self):
		return self.getWatchlist('shows')
	def getWatchlistMovies(self):
		return self.getWatchlist('movies')

	# url: http://api.trakt.tv/<movie|show>/watchlist/<apikey>
	# returns:
	def watchlistAddItems(self, type, data):
			url = "%s/%s/watchlist/%s" % (self.__baseURL, type, self.__apikey)
			Debug("[traktAPI] watchlistAddItem(url: %s)" % url)
			return self.traktRequest('POST', url, data)

	def watchlistAddShows(self, data):
		return self.watchlistAddItems('show', data)
	def watchlistAddMovies(self, data):
		return self.watchlistAddItems('movie', data)

	# url: http://api.trakt.tv/<movie|show>/unwatchlist/<apikey>
	# returns:
	def watchlistRemoveItems(self, type, data):
			url = "%s/%s/unwatchlist/%s" % (self.__baseURL, type, self.__apikey)
			Debug("[traktAPI] watchlistRemoveItems(url: %s)" % url)
			return self.traktRequest('POST', url, data)

	def watchlistRemoveShows(self, data):
		return self.watchlistRemoveItems('show', data)
	def watchlistRemoveMovies(self, data):
		return self.watchlistRemoveItems('movie', data)

	# url: http://api.trakt.tv/users/ratings/<movies|shows>.json/<apikey>/<username>/<rating>
	# returns:
	# note: if no items, returns []
	def getRatedItems(self, type):
			url = "%s/users/%s/ratings/%s/%s/" % (self.__baseURL, self.__username, type, self.__apikey)
			Debug("[traktAPI] getRatedItems(url: %s)" % url)
			return self.traktRequest('POST', url)

	def getRatedMovies(self):
		return self.getRatedItems('movies')
	def getRatedShows(self):
		return self.getRatedItems('shows')
