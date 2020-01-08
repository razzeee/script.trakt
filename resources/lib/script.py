# -*- coding: utf-8 -*-
import xbmc
import sys
import logging
from resources.lib import utilities
from resources.lib import kodiUtilities
from resources.lib import sqlitequeue
from resources.lib.traktContextMenu import traktContextMenu

logger = logging.getLogger(__name__)


def __getArguments():
    data = None
    default_actions = {0: "sync"}
    if len(sys.argv) == 1:
        data = {'action': default_actions[0]}
    else:
        data = {}
        for item in sys.argv:
            values = item.split("=")
            if len(values) == 2:
                data[values[0].lower()] = values[1]
        data['action'] = data['action'].lower()

    return data

def run():
    args = __getArguments()
    data = {}

    if args['action'] == 'auth_info':
        data['action'] = 'auth_info'

    if args['action'] == 'contextmenu':
        buttons = []
        media_type = kodiUtilities.getMediaType()

        if media_type in ['movie', 'show', 'season', 'episode']:
            buttons.append("rate")
            buttons.append("togglewatched")
            buttons.append("addtowatchlist")

        buttons.append("sync")

        contextMenu = traktContextMenu(media_type=media_type, buttons=buttons)
        contextMenu.doModal()
        _action = contextMenu.action
        del contextMenu

        if _action is None:
            return

        logger.debug("'%s' selected from trakt.tv action menu" % _action)
        args['action'] = _action

    if args['action'] == 'sync':
        data = {'action': 'manualSync', 'silent': False}
        if 'silent' in args:
            data['silent'] = (args['silent'].lower() == 'true')
        data['library'] = "all"
        if 'library' in args and args['library'] in ['episodes', 'movies']:
            data['library'] = args['library']

    elif args['action'] in ['rate', 'unrate']:
        data = {'action': args['action']}
        media_type = None
        if 'media_type' in args and 'dbid' in args:
            media_type = args['media_type']
            try:
                data['dbid'] = int(args['dbid'])
            except ValueError:
                logger.debug("Manual %s triggered for library item, but DBID is invalid." % args['action'])
                return
        elif 'media_type' in args and 'remoteid' in args:
            media_type = args['media_type']
            data['remoteid'] = args['remoteid']
            try:
                data['season'] = int(args['season'])
                data['episode'] = int(args['episode'])
            except ValueError:
                logger.debug("Error parsing season or episode for manual %s" % args['action'])
                return
            except KeyError:
                pass
        else:
            media_type = kodiUtilities.getMediaType()
            if not utilities.isValidMediaType(media_type):
                logger.debug("Error, not in video library.")
                return
            data['dbid'] = int(xbmc.getInfoLabel('ListItem.DBID'))

        if media_type is None:
            logger.debug("Manual %s triggered on an unsupported content container." % args['action'])
        elif utilities.isValidMediaType(media_type):
            data['media_type'] = media_type
            if 'dbid' in data:
                logger.debug("Manual %s of library '%s' with an ID of '%s'." % (args['action'], media_type, data['dbid']))
                if utilities.isMovie(media_type):
                    result = kodiUtilities.getMovieDetailsFromKodi(data['dbid'], ['imdbnumber', 'uniqueid', 'title', 'year'])
                    if not result:
                        logger.debug("No data was returned from Kodi, aborting manual %s." % args['action'])
                        return

                elif utilities.isShow(media_type):
                    tvshow_id = data['dbid']

                elif utilities.isSeason(media_type):
                    result = kodiUtilities.getSeasonDetailsFromKodi(data['dbid'], ['tvshowid', 'season'])
                    if not result:
                        logger.debug("No data was returned from Kodi, aborting manual %s." % args['action'])
                        return
                    tvshow_id = result['tvshowid']
                    data['season'] = result['season']

                elif utilities.isEpisode(media_type):
                    result = kodiUtilities.getEpisodeDetailsFromKodi(data['dbid'], ['season', 'episode', 'tvshowid'])
                    if not result:
                        logger.debug("No data was returned from Kodi, aborting manual %s." % args['action'])
                        return
                    tvshow_id = result['tvshowid']
                    data['season'] = result['season']
                    data['episode'] = result['episode']

                if utilities.isShow(media_type) or utilities.isSeason(media_type) or utilities.isEpisode(media_type):
                    result = kodiUtilities.getShowDetailsFromKodi(tvshow_id, ['imdbnumber', 'uniqueid'])
                    if not result:
                        logger.debug("No data was returned from Kodi, aborting manual %s." % args['action'])
                        return

                data['video_ids'] = result['uniqueid']
            else:
                data['video_id'] = data['remoteid']
                if 'season' in data and 'episode' in data:
                    logger.debug("Manual %s of non-library '%s' S%02dE%02d, with an ID of '%s'." % (args['action'], media_type, data['season'], data['episode'], data['remoteid']))
                elif 'season' in data:
                    logger.debug("Manual %s of non-library '%s' S%02d, with an ID of '%s'." % (args['action'], media_type, data['season'], data['remoteid']))
                else:
                    logger.debug("Manual %s of non-library '%s' with an ID of '%s'." % (args['action'], media_type, data['remoteid']))

            if args['action'] == 'rate' and 'rating' in args:
                if args['rating'] in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']:
                    data['rating'] = int(args['rating'])

            data = {'action': 'manualRating', 'ratingData': data}

        else:
            logger.debug("Manual %s of '%s' is unsupported." % (args['action'], media_type))

    elif args['action'] == 'togglewatched':
        media_type = kodiUtilities.getMediaType()
        if media_type in ['movie', 'show', 'season', 'episode']:
            data = {'media_type': media_type}
            if utilities.isMovie(media_type):
                dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
                result = kodiUtilities.getMovieDetailsFromKodi(
                    dbid, ['imdbnumber', 'uniqueid', 'title', 'year', 'playcount'])
                if result:
                    if result['playcount'] == 0:
                        data['ids'] = result['uniqueid']
                    else:
                        logger.debug("Movie alread marked as watched in Kodi.")
                else:
                    logger.debug("Error getting movie details from Kodi.")
                    return

            elif utilities.isEpisode(media_type):
                dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
                result = kodiUtilities.getEpisodeDetailsFromKodi(dbid, ['showtitle', 'season', 'episode', 'tvshowid', 'playcount'])
                if result:
                    if result['playcount'] == 0:
                        data['ids'] = result['show_ids']
                        data['season'] = result['season']
                        data['number'] = result['episode']
                        data['title'] = result['showtitle']
                    else:
                        logger.debug(
                            "Episode already marked as watched in Kodi.")
                else:
                    logger.debug("Error getting episode details from Kodi.")
                    return

            elif utilities.isSeason(media_type):
                showID = None
                showTitle = xbmc.getInfoLabel('ListItem.TVShowTitle')
                result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShows', 'params': {
                                                       'properties': ['title', 'imdbnumber', 'uniqueid', 'year']}, 'id': 0})
                if result and 'tvshows' in result:
                    for show in result['tvshows']:
                        if show['title'] == showTitle:
                            showID = show['tvshowid']
                            data['ids'] = show['uniqueid']
                            data['title'] = show['title']
                            break
                else:
                    logger.debug("Error getting TV shows from Kodi.")
                    return

                season = xbmc.getInfoLabel('ListItem.Season')
                if season == "":
                    season = 0
                else:
                    season = int(season)

                result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': showID, 'season': season, 'properties': ['season', 'episode', 'playcount']}, 'id': 0})
                if result and 'episodes' in result:
                    episodes = []
                    for episode in result['episodes']:
                        if episode['playcount'] == 0:
                            episodes.append(episode['episode'])

                    if len(episodes) == 0:
                        logger.debug("'%s - Season %d' is already marked as watched." % (showTitle, season))
                        return

                    data['season'] = season
                    data['episodes'] = episodes
                else:
                    logger.debug("Error getting episodes from '%s' for Season %d" % (showTitle, season))
                    return

            elif utilities.isShow(media_type):
                dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
                result = kodiUtilities.getShowDetailsFromKodi(dbid, ['year', 'imdbnumber', 'uniqueid'])
                if not result:
                    logger.debug("Error getting show details from Kodi.")
                    return
                showTitle = result['label']
                data['ids'] = result['uniqueid']
                result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': dbid, 'properties': ['season', 'episode', 'playcount', 'showtitle']}, 'id': 0})
                if result and 'episodes' in result:
                    i = 0
                    s = {}
                    for e in result['episodes']:
                        data['title'] = e['showtitle']
                        season = str(e['season'])
                        if not season in s:
                            s[season] = []
                        if e['playcount'] == 0:
                            s[season].append(e['episode'])
                            i += 1

                    if i == 0:
                        logger.debug("'%s' is already marked as watched." % showTitle)
                        return

                    data['seasons'] = dict((k, v) for k, v in list(s.items()) if v)
                else:
                    logger.debug("Error getting episode details for '%s' from Kodi." % showTitle)
                    return

            if len(data) > 1:
                logger.debug("Marking '%s' with the following data '%s' as watched on Trakt.tv" % (media_type, str(data)))
                data['action'] = 'markWatched'

        # execute toggle watched action
        xbmc.executebuiltin("Action(ToggleWatched)")

    elif args['action'] == 'addtowatchlist':
        media_type = kodiUtilities.getMediaType()
        if media_type in ['movie', 'show', 'season', 'episode']:
            data = {'media_type': media_type}
            if utilities.isMovie(media_type):
                dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
                result = kodiUtilities.getMovieDetailsFromKodi(
                    dbid, ['imdbnumber', 'uniqueid', 'title', 'year', 'playcount'])
                if result:
                    data['ids'] = result['uniqueid']

                else:
                    logger.debug("Error getting movie details from Kodi.")
                    return

            elif utilities.isEpisode(media_type):
                dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
                    result = kodiUtilities.getEpisodeDetailsFromKodi(dbid, ['showtitle', 'season', 'episode', 'tvshowid', 'playcount'])
                if result:
                    data['ids'] = result['show_ids']
                    data['season'] = result['season']
                    data['number'] = result['episode']
                    data['title'] = result['showtitle']

                else:
                    logger.debug("Error getting episode details from Kodi.")
                    return

            elif utilities.isSeason(media_type):
                showID = None
                showTitle = xbmc.getInfoLabel('ListItem.TVShowTitle')
                result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShows', 'params': {
                                                       'properties': ['title', 'imdbnumber', 'uniqueid', 'year']}, 'id': 0})
                if result and 'tvshows' in result:
                    for show in result['tvshows']:
                        if show['title'] == showTitle:
                            showID = show['tvshowid']
                            data['id'] = show['imdbnumber']
                            data['title'] = show['title']
                            break
                else:
                    logger.debug("Error getting TV shows from Kodi.")
                    return

                season = xbmc.getInfoLabel('ListItem.Season')
                if season == "":
                    season = 0
                else:
                    season = int(season)

                result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes',
                                                        'params': {'tvshowid': showID, 'season': season,
                                                                   'properties': ['season', 'episode', 'playcount']},
                                                        'id': 0})
                if result and 'episodes' in result:
                    episodes = []
                    for episode in result['episodes']:
                        if episode['playcount'] == 0:
                            episodes.append(episode['episode'])

                    data['season'] = season
                    data['episodes'] = episodes
                else:
                        logger.debug("Error getting episodes from '%s' for Season %d" % (showTitle, season))
                    return

            elif utilities.isShow(media_type):
                dbid = int(xbmc.getInfoLabel('ListItem.DBID'))
                    result = kodiUtilities.getShowDetailsFromKodi(dbid, ['year', 'imdbnumber', 'uniqueid'])
                if not result:
                    logger.debug("Error getting show details from Kodi.")
                    return
                showTitle = result['label']
                data['ids'] = result['uniqueid']
                result = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes',
                                                        'params': {'tvshowid': dbid, 'properties':
                                                                   ['season', 'episode', 'playcount', 'showtitle']}, 'id': 0})
                if result and 'episodes' in result:
                    s = {}
                    for e in result['episodes']:
                        data['title'] = e['showtitle']
                        season = str(e['season'])
                        if not season in s:
                            s[season] = []
                        if e['playcount'] == 0:
                            s[season].append(e['episode'])

                        data['seasons'] = dict((k, v) for k, v in list(s.items()) if v)
                else:
                        logger.debug("Error getting episode details for '%s' from Kodi." % showTitle)
                    return

            if len(data) > 1:
                logger.debug("Adding '%s' with the following data '%s' to users watchlist on Trakt.tv"
                             % (media_type, str(data)))
                data['action'] = 'addtowatchlist'


    q = sqlitequeue.SqliteQueue()
    if 'action' in data:
        logger.debug("Queuing for dispatch: %s" % data)
        q.append(data)

