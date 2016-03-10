# -*- coding: utf-8 -*-
#

import xbmc
import xbmcaddon
import re
import sys
import logging
import utilities


if sys.version_info >= (2, 7):
    import json as json
else:
    import simplejson as json

# read settings
__addon__ = xbmcaddon.Addon('script.trakt')

logger = logging.getLogger(__name__)

REGEX_URL = '(^https?://)(.+)'

def notification(header, message, time=5000, icon=__addon__.getAddonInfo('icon')):
    xbmc.executebuiltin("XBMC.Notification(%s,%s,%i,%s)" % (header, message, time, icon))

def showSettings():
    __addon__.openSettings()

def getSetting(setting):
    return __addon__.getSetting(setting).strip().decode('utf-8')

def setSetting(setting, value):
    __addon__.setSetting(setting, str(value))

def getSettingAsBool(setting):
    return getSetting(setting).lower() == "true"

def getSettingAsFloat(setting):
    try:
        return float(getSetting(setting))
    except ValueError:
        return 0

def getSettingAsInt(setting):
    try:
        return int(getSettingAsFloat(setting))
    except ValueError:
        return 0

def getString(string_id):
    return __addon__.getLocalizedString(string_id).encode('utf-8', 'ignore')

def kodiJsonRequest(params):
    data = json.dumps(params)
    request = xbmc.executeJSONRPC(data)

    try:
        response = json.loads(request)
    except UnicodeDecodeError:
        response = json.loads(request.decode('utf-8', 'ignore'))

    try:
        if 'result' in response:
            return response['result']
        return None
    except KeyError:
        logger.warn("[%s] %s" % (params['method'], response['error']['message']))
        return None

# check exclusion settings for filename passed as argument
def checkExclusion(fullpath):

    if not fullpath:
        return True

    # Live TV exclusion
    if fullpath.startswith("pvr://") and getSettingAsBool('ExcludeLiveTV'):
        logger.debug("checkExclusion(): Video is playing via Live TV, which is currently set as excluded location.")
        return True

    # HTTP exclusion
    if (fullpath.startswith("http://") or fullpath.startswith("https://")) and getSettingAsBool('ExcludeHTTP'):
        logger.debug("checkExclusion(): Video is playing via HTTP source, which is currently set as excluded location.")
        return True

    # Path exclusions
    ExcludePath = getSetting('ExcludePath').encode('utf-8') # Encode this as fullpath is already encoded
    if ExcludePath != "" and getSettingAsBool('ExcludePathOption'):
        if fullpath.startswith(ExcludePath):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 1.")
            return True
    ExcludePath2 = getSetting('ExcludePath2')
    if ExcludePath2 != "" and getSettingAsBool('ExcludePathOption2'):
        if fullpath.startswith(ExcludePath2):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 2.")
            return True
    ExcludePath3 = getSetting('ExcludePath3')
    if ExcludePath3 != "" and getSettingAsBool('ExcludePathOption3'):
        if fullpath.startswith(ExcludePath3):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 3.")
            return True
    ExcludePath4 = getSetting('ExcludePath4')
    if ExcludePath4 != "" and getSettingAsBool('ExcludePathOption4'):
        if fullpath.startswith(ExcludePath4):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 4.")
            return True
    ExcludePath5 = getSetting('ExcludePath5')
    if ExcludePath5 != "" and getSettingAsBool('ExcludePathOption5'):
        if fullpath.startswith(ExcludePath5):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 5.")
            return True
    ExcludePath6 = getSetting('ExcludePath6')
    if ExcludePath6 != "" and getSettingAsBool('ExcludePathOption6'):
        if fullpath.startswith(ExcludePath6):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 6.")
            return True
    ExcludePath7 = getSetting('ExcludePath7')
    if ExcludePath7 != "" and getSettingAsBool('ExcludePathOption7'):
        if fullpath.startswith(ExcludePath7):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 7.")
            return True
    ExcludePath8 = getSetting('ExcludePath8')
    if ExcludePath8 != "" and getSettingAsBool('ExcludePathOption8'):
        if fullpath.startswith(ExcludePath8):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 8.")
            return True
    ExcludePath9 = getSetting('ExcludePath9')
    if ExcludePath9 != "" and getSettingAsBool('ExcludePathOption9'):
        if fullpath.startswith(ExcludePath9):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 9.")
            return True
    ExcludePath10 = getSetting('ExcludePath10')
    if ExcludePath10 != "" and getSettingAsBool('ExcludePathOption10'):
        if fullpath.startswith(ExcludePath10):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 10.")
            return True
    ExcludePath11 = getSetting('ExcludePath11')
    if ExcludePath11 != "" and getSettingAsBool('ExcludePathOption11'):
        if fullpath.startswith(ExcludePath11):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 11.")
            return True
    ExcludePath12 = getSetting('ExcludePath12')
    if ExcludePath12 != "" and getSettingAsBool('ExcludePathOption12'):
        if fullpath.startswith(ExcludePath12):
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 12.")
            return True

    return False


def kodiRpcToTraktMediaObject(type, data, mode='collected'):
    if type == 'show':
        id = data.pop('imdbnumber')
        data['ids'] = utilities.parseIdToTraktIds(id, type)[0]
        data['rating'] = data['userrating'] if 'userrating' in data and data['userrating'] > 0 else 0
        del(data['label'])
        return data
    elif type == 'episode':
        if checkExclusion(data['file']):
            return

        if data['playcount'] is None:
            plays = 0
        else:
            plays = data.pop('playcount')

        if plays > 0:
            watched = 1
        else:
            watched = 0

        episode = {'season': data['season'], 'number': data['episode'], 'title': data['label'],
                   'ids': {'tvdb': data['uniqueid']['unknown'], 'episodeid': data['episodeid']}, 'watched': watched,
                   'plays': plays, 'collected': 1}
        if 'lastplayed' in data:
            episode['watched_at'] = utilities.convertDateTimeToUTC(data['lastplayed'])
        if 'dateadded' in data:
            episode['collected_at'] = utilities.convertDateTimeToUTC(data['dateadded'])
        if 'runtime' in data:
            episode['runtime'] = data['runtime']
        episode['rating'] = data['userrating'] if 'userrating' in data and data['userrating'] > 0 else 0
        if mode == 'watched' and episode['watched']:
            return episode
        elif mode == 'collected' and episode['collected']:
            return episode
        else:
            return

    elif type == 'movie':
        if checkExclusion(data.pop('file')):
            return
        if 'lastplayed' in data:
            data['watched_at'] = utilities.convertDateTimeToUTC(data.pop('lastplayed'))
        if 'dateadded' in data:
            data['collected_at'] = utilities.convertDateTimeToUTC(data.pop('dateadded'))
        if data['playcount'] is None:
            data['plays'] = 0
        else:
            data['plays'] = data.pop('playcount')
        data['rating'] = data['userrating'] if 'userrating' in data and data['userrating'] > 0 else 0
        data['collected'] = 1  # this is in our kodi so it should be collected
        data['watched'] = 1 if data['plays'] > 0 else 0
        id = data.pop('imdbnumber')
        data['ids'] = utilities.parseIdToTraktIds(id, type)[0]
        del(data['label'])
        return data
    else:
        logger.debug('kodiRpcToTraktMediaObject() No valid type')
        return

def kodiRpcToTraktMediaObjects(data, mode='collected'):
    if 'tvshows' in data:
        shows = data['tvshows']

        # reformat show array
        for show in shows:
            kodiRpcToTraktMediaObject('show', show, mode)
        return shows

    elif 'episodes' in data:
        a_episodes = {}
        seasons = []
        for episode in data['episodes']:
            while not episode['season'] in a_episodes:
                s_no = episode['season']
                a_episodes[s_no] = []
            s_no = episode['season']
            episodeObject = kodiRpcToTraktMediaObject('episode', episode, mode)
            if episodeObject:
                a_episodes[s_no].append(episodeObject)

        for episode in a_episodes:
            seasons.append({'number': episode, 'episodes': a_episodes[episode]})
        return seasons

    elif 'movies' in data:
        movies = data['movies']
        kodi_movies = []

        # reformat movie array
        for movie in movies:
            movieObject = kodiRpcToTraktMediaObject('movie', movie, mode)
            if movieObject:
                kodi_movies.append(movieObject)
        return kodi_movies
    else:
        logger.debug('kodiRpcToTraktMediaObjects() No valid key found in rpc data')
        return

def getFormattedItemName(type, info):
    try:
        if utilities.isShow(type):
            s = info['title']
        elif utilities.isEpisode(type):
                s = "S%02dE%02d - %s" % (info['season'], info['number'], info['title'])
        elif utilities.isSeason(type):
            if info['season'] > 0:
                s = "%s - Season %d" % (info['title'], info['season'])
            else:
                s = "%s - Specials" % info['title']
        elif utilities.isMovie(type):
            s = "%s (%s)" % (info['title'], info['year'])
    except KeyError:
        s = ''
    return s.encode('utf-8', 'ignore')

def getShowDetailsFromKodi(showID, fields):
    result = kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShowDetails', 'params': {'tvshowid': showID, 'properties': fields}, 'id': 1})
    logger.debug("getShowDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getShowDetailsFromKodi(): Result from Kodi was empty.")
        return None

    try:
        return result['tvshowdetails']
    except KeyError:
        logger.debug("getShowDetailsFromKodi(): KeyError: result['tvshowdetails']")
        return None

def getSeasonDetailsFromKodi(seasonID, fields):
    result = kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetSeasonDetails', 'params': {'seasonid': seasonID, 'properties': fields}, 'id': 1})
    logger.debug("getSeasonDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getSeasonDetailsFromKodi(): Result from Kodi was empty.")
        return None

    try:
        return result['seasondetails']
    except KeyError:
        logger.debug("getSeasonDetailsFromKodi(): KeyError: result['seasondetails']")
        return None

# get a single episode from kodi given the id
def getEpisodeDetailsFromKodi(libraryId, fields):
    result = kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodeDetails', 'params': {'episodeid': libraryId, 'properties': fields}, 'id': 1})
    logger.debug("getEpisodeDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getEpisodeDetailsFromKodi(): Result from Kodi was empty.")
        return None

    show_data = getShowDetailsFromKodi(result['episodedetails']['tvshowid'], ['year', 'imdbnumber'])

    if not show_data:
        logger.debug("getEpisodeDetailsFromKodi(): Result from getShowDetailsFromKodi() was empty.")
        return None

    result['episodedetails']['imdbnumber'] = show_data['imdbnumber']
    result['episodedetails']['year'] = show_data['year']

    try:
        return result['episodedetails']
    except KeyError:
        logger.debug("getEpisodeDetailsFromKodi(): KeyError: result['episodedetails']")
        return None

# get a single movie from kodi given the id
def getMovieDetailsFromKodi(libraryId, fields):
    result = kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetMovieDetails', 'params': {'movieid': libraryId, 'properties': fields}, 'id': 1})
    logger.debug("getMovieDetailsFromKodi(): %s" % str(result))

    if not result:
        logger.debug("getMovieDetailsFromKodi(): Result from Kodi was empty.")
        return None

    try:
        return result['moviedetails']
    except KeyError:
        logger.debug("getMovieDetailsFromKodi(): KeyError: result['moviedetails']")
        return None

def checkAndConfigureProxy():
    proxyActive = kodiJsonRequest({'jsonrpc': '2.0', "method":"Settings.GetSettingValue", "params":{"setting":"network.usehttpproxy"}, 'id': 1})['value']
    proxyType = kodiJsonRequest({'jsonrpc': '2.0', "method":"Settings.GetSettingValue", "params":{"setting":"network.httpproxytype"}, 'id': 1})['value']

    if proxyActive and proxyType == 0: # PROXY_HTTP
        proxyURL = kodiJsonRequest({'jsonrpc': '2.0', "method":"Settings.GetSettingValue", "params":{"setting":"network.httpproxyserver"}, 'id': 1})['value']
        proxyPort = unicode(kodiJsonRequest({'jsonrpc': '2.0', "method":"Settings.GetSettingValue", "params":{"setting":"network.httpproxyport"}, 'id': 1})['value'])
        proxyUsername = kodiJsonRequest({'jsonrpc': '2.0', "method":"Settings.GetSettingValue", "params":{"setting":"network.httpproxyusername"}, 'id': 1})['value']
        proxyPassword = kodiJsonRequest({'jsonrpc': '2.0', "method":"Settings.GetSettingValue", "params":{"setting":"network.httpproxypassword"}, 'id': 1})['value']

        if proxyUsername and proxyPassword and proxyURL and proxyPort:
            regexUrl = re.compile(REGEX_URL)
            matchURL = regexUrl.search(proxyURL)
            if matchURL:
                return matchURL.group(1) + proxyUsername + ':' + proxyPassword + '@' + matchURL.group(2) + ':' + proxyPort
        elif proxyURL and proxyPort:
            return proxyURL + ':' + proxyPort
    
    return None

def getMediaType():
    if xbmc.getCondVisibility('Container.Content(tvshows)'):
        return "show"
    elif xbmc.getCondVisibility('Container.Content(seasons)'):
        return "season"
    elif xbmc.getCondVisibility('Container.Content(episodes)'):
        return "episode"
    elif xbmc.getCondVisibility('Container.Content(movies)'):
        return "movie"
    else:
        return None

