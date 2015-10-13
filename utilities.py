# -*- coding: utf-8 -*-
#

import xbmc
import xbmcaddon
import time
import re
import sys
import logging
import traceback
import dateutil.parser
from datetime import datetime
from dateutil.tz import tzutc, tzlocal


if sys.version_info >= (2, 7):
    import json as json
else:
    import simplejson as json

# read settings
__addon__ = xbmcaddon.Addon('script.trakt')

# make strptime call prior to doing anything, to try and prevent threading errors
time.strptime("1970-01-01 12:00:00", "%Y-%m-%d %H:%M:%S")

logger = logging.getLogger(__name__)

REGEX_EXPRESSIONS = ['[Ss]([0-9]+)[][._-]*[Ee]([0-9]+)([^\\\\/]*)$',
                      '[\._ \-]([0-9]+)x([0-9]+)([^\\/]*)',  # foo.1x09
                      '[\._ \-]([0-9]+)([0-9][0-9])([\._ \-][^\\/]*)',  # foo.109
                      '([0-9]+)([0-9][0-9])([\._ \-][^\\/]*)',
                      '[\\\\/\\._ -]([0-9]+)([0-9][0-9])[^\\/]*',
                      'Season ([0-9]+) - Episode ([0-9]+)[^\\/]*',  # Season 01 - Episode 02
                      'Season ([0-9]+) Episode ([0-9]+)[^\\/]*',  # Season 01 Episode 02
                      '[\\\\/\\._ -][0]*([0-9]+)x[0]*([0-9]+)[^\\/]*',
                      '[[Ss]([0-9]+)\]_\[[Ee]([0-9]+)([^\\/]*)',  # foo_[s01]_[e01]
                      '[\._ \-][Ss]([0-9]+)[\.\-]?[Ee]([0-9]+)([^\\/]*)',  # foo, s01e01, foo.s01.e01, foo.s01-e01
                      's([0-9]+)ep([0-9]+)[^\\/]*',  # foo - s01ep03, foo - s1ep03
                      '[Ss]([0-9]+)[][ ._-]*[Ee]([0-9]+)([^\\\\/]*)$',
                      '[\\\\/\\._ \\[\\(-]([0-9]+)x([0-9]+)([^\\\\/]*)$'
                     ]

REGEX_YEAR = '^(.+) \((\d{4})\)$'

REGEX_URL = '(^https?://)(.+)'

def notification(header, message, time=5000, icon=__addon__.getAddonInfo('icon')):
    xbmc.executebuiltin("XBMC.Notification(%s,%s,%i,%s)" % (header, message, time, icon))

def showSettings():
    __addon__.openSettings()

def getSetting(setting):
    return __addon__.getSetting(setting).strip()

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

def isMovie(type):
    return type == 'movie'

def isEpisode(type):
    return type == 'episode'

def isShow(type):
    return type == 'show'

def isSeason(type):
    return type == 'season'

def isValidMediaType(type):
    return type in ['movie', 'show', 'season', 'episode']

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

def chunks(l, n):
    return [l[i:i + n] for i in range(0, len(l), n)]

# check exclusion settings for filename passed as argument
def checkExclusion(fullpath):

    if not fullpath:
        return True

    # Live TV exclusion
    if (fullpath.find("pvr://") > -1) and getSettingAsBool('ExcludeLiveTV'):
        logger.debug("checkExclusion(): Video is playing via Live TV, which is currently set as excluded location.")
        return True

    # HTTP exclusion
    if (fullpath.find("http://") > -1) and getSettingAsBool('ExcludeHTTP'):
        logger.debug("checkExclusion(): Video is playing via HTTP source, which is currently set as excluded location.")
        return True

    # Path exclusions
    ExcludePath = getSetting('ExcludePath')
    if ExcludePath != "" and getSettingAsBool('ExcludePathOption'):
        if fullpath.find(ExcludePath) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 1.")
            return True
    ExcludePath2 = getSetting('ExcludePath2')
    if ExcludePath2 != "" and getSettingAsBool('ExcludePathOption2'):
        if fullpath.find(ExcludePath2) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 2.")
            return True
    ExcludePath3 = getSetting('ExcludePath3')
    if ExcludePath3 != "" and getSettingAsBool('ExcludePathOption3'):
        if fullpath.find(ExcludePath3) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 3.")
            return True
    ExcludePath4 = getSetting('ExcludePath4')
    if ExcludePath4 != "" and getSettingAsBool('ExcludePathOption'):
        if fullpath.find(ExcludePath4) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 4.")
            return True
    ExcludePath5 = getSetting('ExcludePath5')
    if ExcludePath5 != "" and getSettingAsBool('ExcludePathOption2'):
        if fullpath.find(ExcludePath5) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 5.")
            return True
    ExcludePath6 = getSetting('ExcludePath6')
    if ExcludePath6 != "" and getSettingAsBool('ExcludePathOption3'):
        if fullpath.find(ExcludePath6) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 6.")
            return True
    ExcludePath7 = getSetting('ExcludePath7')
    if ExcludePath7 != "" and getSettingAsBool('ExcludePathOption'):
        if fullpath.find(ExcludePath7) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 7.")
            return True
    ExcludePath8 = getSetting('ExcludePath8')
    if ExcludePath8 != "" and getSettingAsBool('ExcludePathOption2'):
        if fullpath.find(ExcludePath8) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 8.")
            return True
    ExcludePath9 = getSetting('ExcludePath9')
    if ExcludePath9 != "" and getSettingAsBool('ExcludePathOption3'):
        if fullpath.find(ExcludePath9) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 9.")
            return True
    ExcludePath10 = getSetting('ExcludePath10')
    if ExcludePath10 != "" and getSettingAsBool('ExcludePathOption'):
        if fullpath.find(ExcludePath10) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 10.")
            return True
    ExcludePath11 = getSetting('ExcludePath11')
    if ExcludePath11 != "" and getSettingAsBool('ExcludePathOption2'):
        if fullpath.find(ExcludePath11) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 11.")
            return True
    ExcludePath12 = getSetting('ExcludePath12')
    if ExcludePath12 != "" and getSettingAsBool('ExcludePathOption3'):
        if fullpath.find(ExcludePath12) > -1:
            logger.debug("checkExclusion(): Video is from location, which is currently set as excluded path 12.")
            return True

    return False

def getFormattedItemName(type, info):
    try:
        if isShow(type):
            s = info['title']
        elif isEpisode(type):
                s = "S%02dE%02d - %s" % (info['season'], info['number'], info['title'])
        elif isSeason(type):
            if info['season'] > 0:
                s = "%s - Season %d" % (info['title'], info['season'])
            else:
                s = "%s - Specials" % info['title']
        elif isMovie(type):
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

def __findInList(list, case_sensitive=True, **kwargs):
    for item in list:
        i = 0
        for key in kwargs:
            # becuause we can need to find at the root level and inside ids this is is required
            if key in item:
                key_val = item[key]
            else:
                if 'ids' in item and key in item['ids']:
                    key_val = item['ids'][key]
                else:
                    continue
            if not case_sensitive and isinstance(key_val, basestring):
                if key_val.lower() == kwargs[key].lower():
                    i = i + 1
            else:
                # forcing the compare to be done at the string level
                if unicode(key_val) == unicode(kwargs[key]):
                    i = i + 1
        if i == len(kwargs):
            return item
    return None

def findMediaObject(mediaObjectToMatch, listToSearch):
    result = None
    if result is None and 'ids' in mediaObjectToMatch and 'imdb' in mediaObjectToMatch['ids'] and unicode(mediaObjectToMatch['ids']['imdb']).startswith("tt"):
        result = __findInList(listToSearch, imdb=mediaObjectToMatch['ids']['imdb'])
    # we don't want to give up if we don't find a match based on the first field so we use if instead of elif
    if result is None and 'ids' in mediaObjectToMatch and 'tmdb' in mediaObjectToMatch['ids'] and mediaObjectToMatch['ids']['tmdb'].isdigit():
        result = __findInList(listToSearch, tmdb=mediaObjectToMatch['ids']['tmdb'])
    if result is None and 'ids' in mediaObjectToMatch and 'tvdb' in mediaObjectToMatch['ids'] and mediaObjectToMatch['ids']['tvdb'].isdigit():
        result = __findInList(listToSearch, tvdb=mediaObjectToMatch['ids']['tvdb'])
    # match by title and year it will result in movies with the same title and year to mismatch - but what should we do instead?
    if result is None and 'title' in mediaObjectToMatch and 'year' in mediaObjectToMatch:
        result = __findInList(listToSearch, title=mediaObjectToMatch['title'], year=mediaObjectToMatch['year'])
    return result

def regex_tvshow(compare, file, sub=""):
    tvshow = 0

    for regex in REGEX_EXPRESSIONS:
        response_file = re.findall(regex, file)
        if len(response_file) > 0:
            logger.debug("regex_tvshow(): Regex File Se: %s, Ep: %s," % (str(response_file[0][0]), str(response_file[0][1]),))
            tvshow = 1
            if not compare:
                title = re.split(regex, file)[0]
                for char in ['[', ']', '_', '(', ')', '.', '-']:
                    title = title.replace(char, ' ')
                if title.endswith(" "):
                    title = title[:-1]
                return title, response_file[0][0], response_file[0][1]
            else:
                break

    if tvshow == 1:
        for regex in REGEX_EXPRESSIONS:
            response_sub = re.findall(regex, sub)
            if len(response_sub) > 0:
                try:
                    if int(response_sub[0][1]) == int(response_file[0][1]):
                        return True
                except:
                    pass
        return False
    if compare:
        return True
    else:
        return "", "", ""

def regex_year(title):
    prog = re.compile(REGEX_YEAR)
    result = prog.match(title)

    if result:
        return result.group(1), result.group(2)
    else:
        return "", ""

def findMovieMatchInList(id, list, idType):
    return next((item.to_dict() for key, item in list.items() if any(idType in key for key, value in item.keys if str(value) == str(id))), {})

def findShowMatchInList(id, list, idType):
    return next((item.to_dict() for key, item in list.items() if  any(idType in key for key, value in item.keys if str(value) == str(id))), {})

def findSeasonMatchInList(id, seasonNumber, list, idType):
    show = findShowMatchInList(id, list, idType)
    logger.debug("findSeasonMatchInList %s" % show)
    if 'seasons' in show:
        for season in show['seasons']:
            if season['number'] == seasonNumber:
                return season

    return {}

def findEpisodeMatchInList(id, seasonNumber, episodeNumber, list, idType):
    season = findSeasonMatchInList(id, seasonNumber, list, idType)
    if season:
        for episode in season['episodes']:
            if episode['number'] == episodeNumber:
                return episode

    return {}

def kodiRpcToTraktMediaObject(type, data, mode='collected'):
    if type == 'show':
        id = data.pop('imdbnumber')
        data['ids'] = parseIdToTraktIds(id, type)[0]
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
                    'ids': {'tvdb': data['uniqueid']['unknown'], 'episodeid': data['episodeid']}, 'watched': watched, 'plays': plays}
        episode['collected'] = 1  # this is in our kodi so it should be collected
        if 'lastplayed' in data:
            episode['watched_at'] = convertDateTimeToUTC(data['lastplayed'])
        if 'dateadded' in data:
            episode['collected_at'] = convertDateTimeToUTC(data['dateadded'])
        if 'runtime' in data:
            episode['runtime'] = data['runtime']
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
            data['watched_at'] = convertDateTimeToUTC(data.pop('lastplayed'))
        if 'dateadded' in data:
            data['collected_at'] = convertDateTimeToUTC(data.pop('dateadded'))
        if data['playcount'] is None:
            data['plays'] = 0
        else:
            data['plays'] = data.pop('playcount')
        data['collected'] = 1  # this is in our kodi so it should be collected
        data['watched'] = 1 if data['plays'] > 0 else 0
        id = data.pop('imdbnumber')
        data['ids'] = parseIdToTraktIds(id, type)[0]
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

def convertDateTimeToUTC(toConvert):
    if toConvert:
        dateFormat = "%Y-%m-%d %H:%M:%S"
        try:
            naive = datetime.strptime(toConvert, dateFormat)
        except TypeError:
            naive = datetime(*(time.strptime(toConvert, dateFormat)[0:6]))
        if 2038 < naive.year  or 1970 > naive.year:
            logger.debug('convertDateTimeToUTC() Movie/show was collected/watched outside of the unix timespan. Fallback to datetime now')
            naive = datetime.strptime(str(datetime.now()).split(".")[0], dateFormat)
        local = naive.replace(tzinfo=tzlocal())
        utc = local.astimezone(tzutc())
        return unicode(utc)

    else:
        return toConvert

def convertUtcToDateTime(toConvert):
    if toConvert:
        dateFormat = "%Y-%m-%d %H:%M:%S"
        naive = dateutil.parser.parse(toConvert)
        if 2038 < naive.year  or 1970 > naive.year:
            logger.debug('convertUtcToDateTime() Movie/show was collected/watched outside of the unix timespan. Fallback to datetime now')
            naive = datetime.strptime(str(datetime.now()).split(".")[0], dateFormat)
        utc = naive.replace(tzinfo=tzutc())
        local = utc.astimezone(tzlocal())

        return local.strftime(dateFormat)
    else:
        return toConvert

def createError(ex):
    template = (
            "EXCEPTION Thrown (PythonToCppException) : -->Python callback/script returned the following error<--\n"
            " - NOTE: IGNORING THIS CAN LEAD TO MEMORY LEAKS!\n"
            "Error Type: <type '{0}'>\n"
            "Error Contents: {1!r}\n"
            "{2}"
            "-->End of Python script error report<--"
            )
    return template.format(type(ex).__name__, ex.args, traceback.format_exc())

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
            else:
                None
        elif proxyURL and proxyPort:
            return proxyURL + ':' + proxyPort
    else:
        return None

def parseIdToTraktIds(id, type):
    data = {}
    id_type = ''
    if id.startswith("tt"):
        data['imdb'] = id
        id_type = 'imdb'
    elif id.isdigit() and isMovie(type):
        data['tmdb'] = id
        id_type = 'tmdb'
    elif id.isdigit() and (isEpisode(type) or isSeason(type) or isShow(type)):
        data['tvdb'] = id
        id_type = 'tvdb'
    else:
        data['slug'] = id
        id_type = 'slug'
    return data, id_type

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

def best_id(ids):
    if 'trakt' in ids:
        return ids['trakt']
    elif 'imdb' in ids:
        return ids['imdb']
    elif 'tmdb' in ids:
        return ids['tmdb']
    elif 'tvdb' in ids:
        return ids['tvdb']
    elif 'tvrage' in ids:
        return ids['tvrage']
    elif 'slug' in ids:
        return ids['slug']
