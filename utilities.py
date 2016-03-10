# -*- coding: utf-8 -*-
#

import time
import re
import logging
import traceback
import dateutil.parser
from datetime import datetime
from dateutil.tz import tzutc, tzlocal

# make strptime call prior to doing anything, to try and prevent threading errors
time.strptime("1970-01-01 12:00:00", "%Y-%m-%d %H:%M:%S")

logger = logging.getLogger(__name__)

REGEX_YEAR = '^(.+) \((\d{4})\)$'


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

def chunks(l, n):
    return [l[i:i + n] for i in range(0, len(l), n)]

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

def __findInList(list, case_sensitive=True, **kwargs):
    for item in list:
        i = 0
        for key in kwargs:
            # because we can need to find at the root level and inside ids this is is required
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

def regex_tvshow(label):
    regexes = [
        '(.*?)[._ -]s([0-9]+)[._ -]*e([0-9]+)',  # ShowTitle.S01E09; s01e09, s01.e09, s01-e09
        '(.*?)[._ -]([0-9]+)x([0-9]+)',  # Showtitle.1x09
        '(.*?)[._ -]([0-9]+)([0-9][0-9])',  # ShowTitle.109
        '(.*?)[._ -]?season[._ -]*([0-9]+)[._ -]*-?[._ -]*episode[._ -]*([0-9]+)',  # ShowTitle.Season 01 - Episode 02, Season 01 Episode 02
        '(.*?)[._ -]\[s([0-9]+)\][._ -]*\[[e]([0-9]+)',  # ShowTitle_[s01]_[e01]
        '(.*?)[._ -]s([0-9]+)[._ -]*ep([0-9]+)']  # ShowTitle - s01ep03, ShowTitle - s1ep03
    
    for regex in regexes:
        match = re.search(regex, label, re.I)
        if match:
            show_title, season, episode = match.groups()
            if show_title:
                show_title = re.sub('[\[\]_\(\).-]', ' ', show_title)
                show_title = re.sub('\s\s+', ' ', show_title)
                show_title = show_title.strip()
            return show_title, int(season), int(episode)
    
    return '', -1, -1

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

def convertDateTimeToUTC(toConvert):
    if toConvert:
        dateFormat = "%Y-%m-%d %H:%M:%S"
        try: naive = datetime.strptime(toConvert, dateFormat)
        except TypeError: naive = datetime(*(time.strptime(toConvert, dateFormat)[0:6]))
		
        try:
            local = naive.replace(tzinfo=tzlocal())
            utc = local.astimezone(tzutc())
        except ValueError:
            logger.debug('convertDateTimeToUTC() ValueError: movie/show was collected/watched outside of the unix timespan. Fallback to datetime utcnow')
            utc = datetime.utcnow()
        return unicode(utc)
    else:
        return toConvert

def convertUtcToDateTime(toConvert):
    if toConvert:
        dateFormat = "%Y-%m-%d %H:%M:%S"
        try:
            naive = dateutil.parser.parse(toConvert)
            utc = naive.replace(tzinfo=tzutc())
            local = utc.astimezone(tzlocal())
        except ValueError:
            logger.debug('convertUtcToDateTime() ValueError: movie/show was collected/watched outside of the unix timespan. Fallback to datetime now')
            local = datetime.now()
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
