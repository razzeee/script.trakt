# -*- coding: utf-8 -*-
#

import time
import re
import logging
import traceback
import dateutil.parser
from datetime import datetime
from dateutil.tz import tzutc, tzlocal

# make strptime call prior to doing anything, to try and prevent threading
# errors
time.strptime("1970-01-01 12:00:00", "%Y-%m-%d %H:%M:%S")

logger = logging.getLogger(__name__)


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
    s = ''
    try:
        if isShow(type):
            s = info['title']
        elif isEpisode(type):
            s = "S%02dE%02d - %s" % (info['season'],
                                     info['number'], info['title'])
        elif isSeason(type):
            if isinstance(info, list):
                info = info[0]
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
            # because we can need to find at the root level and inside ids this
            # is is required
            if key in item:
                key_val = item[key]
            else:
                if 'ids' in item and key in item['ids']:
                    key_val = item['ids'][key]
                else:
                    continue
            if not case_sensitive and isinstance(key_val, str):
                if key_val.lower() == kwargs[key].lower():
                    i = i + 1
            else:
                # forcing the compare to be done at the string level
                if str(key_val) == str(kwargs[key]):
                    i = i + 1
        if i == len(kwargs):
            return item
    return None


def findMediaObject(mediaObjectToMatch, listToSearch):
    result = None
    if result is None and 'ids' in mediaObjectToMatch and 'imdb' in mediaObjectToMatch['ids'] and str(mediaObjectToMatch['ids']['imdb']).startswith("tt"):
        result = __findInList(
            listToSearch, imdb=mediaObjectToMatch['ids']['imdb'])
    # we don't want to give up if we don't find a match based on the first
    # field so we use if instead of elif
    if result is None and 'ids' in mediaObjectToMatch and 'tmdb' in mediaObjectToMatch['ids'] and mediaObjectToMatch['ids']['tmdb']:
        result = __findInList(
            listToSearch, tmdb=mediaObjectToMatch['ids']['tmdb'])
    if result is None and 'ids' in mediaObjectToMatch and 'tvdb' in mediaObjectToMatch['ids'] and mediaObjectToMatch['ids']['tvdb']:
        result = __findInList(
            listToSearch, tvdb=mediaObjectToMatch['ids']['tvdb'])
    # match by title and year it will result in movies with the same title and
    # year to mismatch - but what should we do instead?
    if result is None and 'title' in mediaObjectToMatch and 'year' in mediaObjectToMatch:
        result = __findInList(
            listToSearch, title=mediaObjectToMatch['title'], year=mediaObjectToMatch['year'])
    # match only by title, as some items don't have a year on trakt
    if result is None and 'title' in mediaObjectToMatch:
        result = __findInList(
            listToSearch, title=mediaObjectToMatch['title'])
    return result


def regex_tvshow(label):
    regexes = [
        # ShowTitle.S01E09; s01e09, s01.e09, s01-e09
        '(.*?)[._ -]s([0-9]+)[._ -]*e([0-9]+)',
        '(.*?)[._ -]([0-9]+)x([0-9]+)',  # Showtitle.1x09
        '(.*?)[._ -]([0-9]+)([0-9][0-9])',  # ShowTitle.109
        # ShowTitle.Season 01 - Episode 02, Season 01 Episode 02
        '(.*?)[._ -]?season[._ -]*([0-9]+)[._ -]*-?[._ -]*episode[._ -]*([0-9]+)',
        # ShowTitle_[s01]_[e01]
        '(.*?)[._ -]\[s([0-9]+)\][._ -]*\[[e]([0-9]+)',
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
    prog = re.compile('^(.+) \((\d{4})\)$')
    result = prog.match(title)

    if result:
        return result.group(1), result.group(2)
    else:
        return "", ""


def findMovieMatchInList(id, list, idType):
    return next((item.to_dict() for key, item in list(list.items()) if any(idType in key for key, value in item.keys if str(value) == str(id))), {})


def findShowMatchInList(id, list, idType):
    return next((item.to_dict() for key, item in list(list.items()) if any(idType in key for key, value in item.keys if str(value) == str(id))), {})


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
        try:
            naive = datetime.strptime(toConvert, dateFormat)
        except TypeError:
            naive = datetime(*(time.strptime(toConvert, dateFormat)[0:6]))

        try:
            local = naive.replace(tzinfo=tzlocal())
            utc = local.astimezone(tzutc())
        except ValueError:
            logger.debug(
                'convertDateTimeToUTC() ValueError: movie/show was collected/watched outside of the unix timespan. Fallback to datetime utcnow')
            utc = datetime.utcnow()
        return str(utc)
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
            logger.debug(
                'convertUtcToDateTime() ValueError: movie/show was collected/watched outside of the unix timespan. Fallback to datetime now')
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


def checkExcludePath(excludePath, excludePathEnabled, fullpath, x):
    if excludePath != "" and excludePathEnabled and fullpath.startswith(excludePath):
        logger.debug(
            "checkExclusion(): Video is from location, which is currently set as excluded path %i." % x)
        return True
    else:
        return False


def sanitizeMovies(movies):
    # do not remove watched_at and collected_at may cause problems between the
    # 4 sync types (would probably have to deepcopy etc)
    for movie in movies:
        if 'collected' in movie:
            del movie['collected']
        if 'watched' in movie:
            del movie['watched']
        if 'movieid' in movie:
            del movie['movieid']
        if 'plays' in movie:
            del movie['plays']
        if 'userrating' in movie:
            del movie['userrating']

#todo add tests
def sanitizeShows(shows):
    # do not remove watched_at and collected_at may cause problems between the
    # 4 sync types (would probably have to deepcopy etc)
    for show in shows['shows']:
        for season in show['seasons']:
            for episode in season['episodes']:
                if 'collected' in episode:
                    del episode['collected']
                if 'watched' in episode:
                    del episode['watched']
                if 'season' in episode:
                    del episode['season']
                if 'plays' in episode:
                    del episode['plays']
                if 'ids' in episode and 'episodeid' in episode['ids']:
                    del episode['ids']['episodeid']


def compareMovies(movies_col1, movies_col2, watched=False, restrict=False, playback=False, rating=False):
    movies = []

    for movie_col1 in movies_col1:
        if movie_col1:
            movie_col2 = findMediaObject(movie_col1, movies_col2)
            # logger.debug("movie_col1 %s" % movie_col1)
            # logger.debug("movie_col2 %s" % movie_col2)

            if movie_col2:  # match found
                if watched:  # are we looking for watched items
                    if movie_col2['watched'] == 0 and movie_col1['watched'] == 1:
                        if 'movieid' not in movie_col1:
                            movie_col1['movieid'] = movie_col2['movieid']
                        movies.append(movie_col1)
                elif playback:
                    if 'movieid' not in movie_col1:
                            movie_col1['movieid'] = movie_col2['movieid']
                    movie_col1['runtime'] = movie_col2['runtime']
                    movies.append(movie_col1)
                elif rating:
                    if 'rating' in movie_col1 and movie_col1['rating'] != 0 and ('rating' not in movie_col2 or movie_col2['rating'] == 0):
                        if 'movieid' not in movie_col1:
                            movie_col1['movieid'] = movie_col2['movieid']
                        movies.append(movie_col1)
                else:
                    if 'collected' in movie_col2 and not movie_col2['collected']:
                        movies.append(movie_col1)
            else:  # no match found
                if not restrict:
                    if 'collected' in movie_col1 and movie_col1['collected']:
                        if watched and (movie_col1['watched'] == 1):
                            movies.append(movie_col1)
                        elif rating and movie_col1['rating'] != 0:
                            movies.append(movie_col1)
                        elif not watched and not rating:

                            movies.append(movie_col1)
    return movies