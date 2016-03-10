# -*- coding: utf-8 -*-

import copy
import utilities
import kodiUtilities
import logging
from kodiUtilities import notification

logger = logging.getLogger(__name__)

class SyncEpisodes:
    def __init__(self, sync, progress):
        self.sync = sync
        if not self.sync.show_progress and self.sync.sync_on_update and self.sync.notify and self.sync.notify_during_playback:
            notification('%s %s' % (kodiUtilities.getString(32045), kodiUtilities.getString(32050)), kodiUtilities.getString(32061))  # Sync started
        if self.sync.show_progress and not self.sync.run_silent:
            progress.create("%s %s" % (kodiUtilities.getString(32045), kodiUtilities.getString(32050)), line1=" ", line2=" ", line3=" ")

        kodiShowsCollected, kodiShowsWatched = self.__kodiLoadShows()
        if not isinstance(kodiShowsCollected, list) and not kodiShowsCollected:
            logger.debug("[Episodes Sync] Kodi collected show list is empty, aborting tv show Sync.")
            if self.sync.show_progress and not self.sync.run_silent:
                progress.close()
            return
        if not isinstance(kodiShowsWatched, list) and not kodiShowsWatched:
            logger.debug("[Episodes Sync] Kodi watched show list is empty, aborting tv show Sync.")
            if self.sync.show_progress and not self.sync.run_silent:
                progress.close()
            return

        traktShowsCollected, traktShowsWatched, traktShowsRated, traktEpisodesRated = self.__traktLoadShows()
        if not traktShowsCollected:
            logger.debug("[Episodes Sync] Error getting Trakt.tv collected show list, aborting tv show sync.")
            if self.sync.show_progress and not self.sync.run_silent:
                progress.close()
            return
        if not traktShowsWatched:
            logger.debug("[Episodes Sync] Error getting Trakt.tv watched show list, aborting tv show sync.")
            if self.sync.show_progress and not self.sync.run_silent:
                progress.close()
            return

        traktShowsProgress = self.__traktLoadShowsPlaybackProgress(25, 36)

        self.__addEpisodesToTraktCollection(kodiShowsCollected, traktShowsCollected, 37, 47)

        self.__deleteEpisodesFromTraktCollection(traktShowsCollected, kodiShowsCollected, 48, 58)

        self.__addEpisodesToTraktWatched(kodiShowsWatched, traktShowsWatched, 59, 69)

        self.__addEpisodesToKodiWatched(traktShowsWatched, kodiShowsWatched, kodiShowsCollected, 70, 80)

        self.__addEpisodeProgressToKodi(traktShowsProgress, kodiShowsCollected, 81, 91)

        self.__syncShowsRatings(traktShowsRated, kodiShowsCollected, 92, 95)
        self.__syncEpisodeRatings(traktEpisodesRated, kodiShowsCollected, 96, 99)

        if not self.sync.show_progress and self.sync.sync_on_update and self.sync.notify and self.sync.notify_during_playback:
            notification('%s %s' % (kodiUtilities.getString(32045), kodiUtilities.getString(32050)), kodiUtilities.getString(32062))  # Sync complete

        if self.sync.show_progress and not self.sync.run_silent:
            self.sync.UpdateProgress(100, line1=" ", line2=kodiUtilities.getString(32075), line3=" ")
            progress.close()

        logger.debug("[Episodes Sync] Shows on Trakt.tv (%d), shows in Kodi (%d)." % (len(traktShowsCollected['shows']), len(kodiShowsCollected['shows'])))

        logger.debug("[Episodes Sync] Episodes on Trakt.tv (%d), episodes in Kodi (%d)." % (self.__countEpisodes(traktShowsCollected), self.__countEpisodes(kodiShowsCollected)))
        logger.debug("[Episodes Sync] Complete.")

    ''' begin code for episode sync '''
    def __kodiLoadShows(self):
        self.sync.UpdateProgress(1, line1=kodiUtilities.getString(32094), line2=kodiUtilities.getString(32095))

        logger.debug("[Episodes Sync] Getting show data from Kodi")
        data = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetTVShows', 'params': {'properties': ['title', 'imdbnumber', 'year', 'userrating']}, 'id': 0})
        if data['limits']['total'] == 0:
            logger.debug("[Episodes Sync] Kodi json request was empty.")
            return None, None

        tvshows = kodiUtilities.kodiRpcToTraktMediaObjects(data)
        logger.debug("[Episode Sync] Getting shows from kodi finished %s" % tvshows)

        if tvshows is None:
            return None, None
        self.sync.UpdateProgress(2, line2=kodiUtilities.getString(32096))
        resultCollected = {'shows': []}
        resultWatched = {'shows': []}
        i = 0
        x = float(len(tvshows))
        logger.debug("[Episodes Sync] Getting episode data from Kodi")
        for show_col1 in tvshows:
            i += 1
            y = ((i / x) * 8) + 2
            self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32097) % (i, x))

            show = {'title': show_col1['title'], 'ids': {}, 'year': show_col1['year'], 'rating': show_col1['rating'],
                    'tvshowid': show_col1['tvshowid'], 'seasons': []}

            if 'ids' in show_col1 and 'tvdb' in show_col1['ids']:
                show['ids'] = {'tvdb': show_col1['ids']['tvdb']}

            data = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodes', 'params': {'tvshowid': show_col1['tvshowid'], 'properties': ['season', 'episode', 'playcount', 'uniqueid', 'lastplayed', 'file', 'dateadded', 'runtime', 'userrating']}, 'id': 0})
            if not data:
                logger.debug("[Episodes Sync] There was a problem getting episode data for '%s', aborting sync." % show['title'])
                return None, None
            elif 'episodes' not in data:
                logger.debug("[Episodes Sync] '%s' has no episodes in Kodi." % show['title'])
                continue

            if 'tvshowid' in show_col1:
                del(show_col1['tvshowid'])

            showWatched = copy.deepcopy(show)
            data2 = copy.deepcopy(data)
            show['seasons'] = kodiUtilities.kodiRpcToTraktMediaObjects(data)

            showWatched['seasons'] = kodiUtilities.kodiRpcToTraktMediaObjects(data2, 'watched')

            resultCollected['shows'].append(show)
            resultWatched['shows'].append(showWatched)

        self.sync.UpdateProgress(10, line2=kodiUtilities.getString(32098))
        return resultCollected, resultWatched

    def __traktLoadShows(self):
        self.sync.UpdateProgress(10, line1=kodiUtilities.getString(32099), line2=kodiUtilities.getString(32100))

        logger.debug('[Episodes Sync] Getting episode collection from Trakt.tv')
        try:
            traktShowsCollected = {}
            traktShowsCollected = self.sync.traktapi.getShowsCollected(traktShowsCollected)
            traktShowsCollected = traktShowsCollected.items()

            self.sync.UpdateProgress(12, line2=kodiUtilities.getString(32101))
            traktShowsWatched = {}
            traktShowsWatched = self.sync.traktapi.getShowsWatched(traktShowsWatched)
            traktShowsWatched = traktShowsWatched.items()

            traktShowsRated = {}
            traktShowsRated = self.sync.traktapi.getShowsRated(traktShowsRated)
            traktShowsRated = traktShowsRated.items()

            traktEpisodesRated = {}
            traktEpisodesRated = self.sync.traktapi.getEpisodesRated(traktEpisodesRated)
            traktEpisodesRated = traktEpisodesRated.items()

        except Exception:
            logger.debug("[Episodes Sync] Invalid Trakt.tv show list, possible error getting data from Trakt, aborting Trakt.tv collection update.")
            return False, False

        i = 0
        x = float(len(traktShowsCollected))
        showsCollected = {'shows': []}
        for _, show in traktShowsCollected:
            i += 1
            y = ((i / x) * 4) + 12
            self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32102) % (i, x))

            # will keep the data in python structures - just like the KODI response
            show = show.to_dict()

            showsCollected['shows'].append(show)

        i = 0
        x = float(len(traktShowsWatched))
        showsWatched = {'shows': []}
        for _, show in traktShowsWatched:
            i += 1
            y = ((i / x) * 4) + 16
            self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32102) % (i, x))

            # will keep the data in python structures - just like the KODI response
            show = show.to_dict()

            showsWatched['shows'].append(show)

        i = 0
        x = float(len(traktShowsRated))
        showsRated = {'shows': []}
        for _, show in traktShowsRated:
            i += 1
            y = ((i / x) * 4) + 20
            self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32102) % (i, x))

            # will keep the data in python structures - just like the KODI response
            show = show.to_dict()

            showsRated['shows'].append(show)

        i = 0
        x = float(len(traktEpisodesRated))
        episodesRated = {'shows': []}
        for _, show in traktEpisodesRated:
            i += 1
            y = ((i / x) * 4) + 20
            self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32102) % (i, x))

            # will keep the data in python structures - just like the KODI response
            show = show.to_dict()

            episodesRated['shows'].append(show)

        self.sync.UpdateProgress(25, line2=kodiUtilities.getString(32103))

        return showsCollected, showsWatched, showsRated, episodesRated

    def __traktLoadShowsPlaybackProgress(self, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_episode_playback') and not self.sync.IsCanceled():
            self.sync.UpdateProgress(fromPercent, line1=kodiUtilities.getString(1485), line2=kodiUtilities.getString(32119))

            logger.debug('[Playback Sync] Getting playback progress from Trakt.tv')
            try:
                traktProgressShows = self.sync.traktapi.getEpisodePlaybackProgress()
            except Exception as ex:
                logger.debug("[Playback Sync] Invalid Trakt.tv progress list, possible error getting data from Trakt, aborting Trakt.tv playback update. Error: %s" % ex)
                return False

            i = 0
            x = float(len(traktProgressShows))
            showsProgress = {'shows': []}
            for show in traktProgressShows:
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32120) % (i, x))

                # will keep the data in python structures - just like the KODI response
                show = show.to_dict()

                showsProgress['shows'].append(show)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32121))

            return showsProgress

    def __addEpisodesToTraktCollection(self, kodiShows, traktShows, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('add_episodes_to_trakt') and not self.sync.IsCanceled():
            addTraktShows = copy.deepcopy(traktShows)
            addKodiShows = copy.deepcopy(kodiShows)

            tmpTraktShowsAdd = self.__compareEpisodes(addKodiShows, addTraktShows)
            traktShowsAdd = copy.deepcopy(tmpTraktShowsAdd)
            self.sanitizeShows(traktShowsAdd)
            # logger.debug("traktShowsAdd %s" % traktShowsAdd)

            if len(traktShowsAdd['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1=kodiUtilities.getString(32068), line2=kodiUtilities.getString(32104))
                logger.debug("[Episodes Sync] Trakt.tv episode collection is up to date.")
                return
            logger.debug("[Episodes Sync] %i show(s) have episodes (%d) to be added to your Trakt.tv collection." % (len(traktShowsAdd['shows']), self.__countEpisodes(traktShowsAdd)))
            for show in traktShowsAdd['shows']:
                logger.debug("[Episodes Sync] Episodes added: %s" % self.__getShowAsString(show, short=True))

            self.sync.UpdateProgress(fromPercent, line1=kodiUtilities.getString(32068), line2=kodiUtilities.getString(32067) % (len(traktShowsAdd['shows'])), line3=" ")

            # split episode list into chunks of 50
            chunksize = 1
            chunked_episodes = utilities.chunks(traktShowsAdd['shows'], chunksize)
            errorcount = 0
            i = 0
            x = float(len(traktShowsAdd['shows']))
            for chunk in chunked_episodes:
                if self.sync.IsCanceled():
                    return
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32069) % ((i) * chunksize if (i) * chunksize < x else x, x))

                request = {'shows': chunk}
                logger.debug("[traktAddEpisodes] Shows to add %s" % request)
                try:
                    self.sync.traktapi.addToCollection(request)
                except Exception as ex:
                    message = utilities.createError(ex)
                    logging.fatal(message)
                    errorcount += 1

            logger.debug("[traktAddEpisodes] Finished with %d error(s)" % errorcount)
            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32105) % self.__countEpisodes(traktShowsAdd))

    def __deleteEpisodesFromTraktCollection(self, traktShows, kodiShows, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('clean_trakt_episodes') and not self.sync.IsCanceled():
            removeTraktShows = copy.deepcopy(traktShows)
            removeKodiShows = copy.deepcopy(kodiShows)

            traktShowsRemove = self.__compareEpisodes(removeTraktShows, removeKodiShows)
            self.sanitizeShows(traktShowsRemove)

            if len(traktShowsRemove['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1=kodiUtilities.getString(32077), line2=kodiUtilities.getString(32110))
                logger.debug('[Episodes Sync] Trakt.tv episode collection is clean, no episodes to remove.')
                return

            logger.debug("[Episodes Sync] %i show(s) will have episodes removed from Trakt.tv collection." % len(traktShowsRemove['shows']))
            for show in traktShowsRemove['shows']:
                logger.debug("[Episodes Sync] Episodes removed: %s" % self.__getShowAsString(show, short=True))

            self.sync.UpdateProgress(fromPercent, line1=kodiUtilities.getString(32077), line2=kodiUtilities.getString(32111) % self.__countEpisodes(traktShowsRemove), line3=" ")

            logger.debug("[traktRemoveEpisodes] Shows to remove %s" % traktShowsRemove)
            try:
                self.sync.traktapi.removeFromCollection(traktShowsRemove)
            except Exception as ex:
                message = utilities.createError(ex)
                logging.fatal(message)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32112) % self.__countEpisodes(traktShowsRemove), line3=" ")

    def __addEpisodesToTraktWatched(self, kodiShows, traktShows, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_episode_playcount') and not self.sync.IsCanceled():
            updateTraktTraktShows = copy.deepcopy(traktShows)
            updateTraktKodiShows = copy.deepcopy(kodiShows)

            traktShowsUpdate = self.__compareEpisodes(updateTraktKodiShows, updateTraktTraktShows, watched=True)
            self.sanitizeShows(traktShowsUpdate)
            # logger.debug("traktShowsUpdate %s" % traktShowsUpdate)

            if len(traktShowsUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1=kodiUtilities.getString(32071), line2=kodiUtilities.getString(32106))
                logger.debug("[Episodes Sync] Trakt.tv episode playcounts are up to date.")
                return

            logger.debug("[Episodes Sync] %i show(s) are missing playcounts on Trakt.tv" % len(traktShowsUpdate['shows']))
            for show in traktShowsUpdate['shows']:
                logger.debug("[Episodes Sync] Episodes updated: %s" % self.__getShowAsString(show, short=True))

            self.sync.UpdateProgress(fromPercent, line1=kodiUtilities.getString(32071), line2=kodiUtilities.getString(32070) % (len(traktShowsUpdate['shows'])), line3="")
            errorcount = 0
            i = 0
            x = float(len(traktShowsUpdate['shows']))
            for show in traktShowsUpdate['shows']:
                if self.sync.IsCanceled():
                    return
                epCount = self.__countEpisodes([show])
                title = show['title'].encode('utf-8', 'ignore')
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=title, line3=kodiUtilities.getString(32073) % epCount)

                s = {'shows': [show]}
                logger.debug("[traktUpdateEpisodes] Shows to update %s" % s)
                try:
                    self.sync.traktapi.addToHistory(s)
                except Exception as ex:
                    message = utilities.createError(ex)
                    logging.fatal(message)
                    errorcount += 1

            logger.debug("[traktUpdateEpisodes] Finished with %d error(s)" % errorcount)
            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32072) % (len(traktShowsUpdate['shows'])), line3="")

    def __addEpisodesToKodiWatched(self, traktShows, kodiShows, kodiShowsCollected, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('kodi_episode_playcount') and not self.sync.IsCanceled():
            updateKodiTraktShows = copy.deepcopy(traktShows)
            updateKodiKodiShows = copy.deepcopy(kodiShows)

            kodiShowsUpdate = self.__compareEpisodes(updateKodiTraktShows, updateKodiKodiShows, watched=True, restrict=True, collected=kodiShowsCollected)

            if len(kodiShowsUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1=kodiUtilities.getString(32074), line2=kodiUtilities.getString(32107))
                logger.debug("[Episodes Sync] Kodi episode playcounts are up to date.")
                return

            logger.debug("[Episodes Sync] %i show(s) shows are missing playcounts on Kodi" % len(kodiShowsUpdate['shows']))
            for s in ["%s" % self.__getShowAsString(s, short=True) for s in kodiShowsUpdate['shows']]:
                logger.debug("[Episodes Sync] Episodes updated: %s" % s)

            # logger.debug("kodiShowsUpdate: %s" % kodiShowsUpdate)
            episodes = []
            for show in kodiShowsUpdate['shows']:
                for season in show['seasons']:
                    for episode in season['episodes']:
                        episodes.append({'episodeid': episode['ids']['episodeid'], 'playcount': episode['plays'], "lastplayed": utilities.convertUtcToDateTime(episode['last_watched_at'])})

            # split episode list into chunks of 50
            chunksize = 50
            chunked_episodes = utilities.chunks([{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": episodes[i], "id": i} for i in range(len(episodes))], chunksize)
            i = 0
            x = float(len(episodes))
            for chunk in chunked_episodes:
                if self.sync.IsCanceled():
                    return
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32108) % ((i) * chunksize if (i) * chunksize < x else x, x))

                logger.debug("[Episodes Sync] chunk %s" % str(chunk))
                result = kodiUtilities.kodiJsonRequest(chunk)
                logger.debug("[Episodes Sync] result %s" % str(result))

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32109) % len(episodes))

    def __addEpisodeProgressToKodi(self, traktShows, kodiShows, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_episode_playback') and traktShows and not self.sync.IsCanceled():
            updateKodiTraktShows = copy.deepcopy(traktShows)
            updateKodiKodiShows = copy.deepcopy(kodiShows)
            kodiShowsUpdate = self.__compareEpisodes(updateKodiTraktShows, updateKodiKodiShows, restrict=True, playback=True)

            if len(kodiShowsUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1=kodiUtilities.getString(1441), line2=kodiUtilities.getString(32129))
                logger.debug("[Episodes Sync] Kodi episode playbacks are up to date.")
                return

            logger.debug("[Episodes Sync] %i show(s) shows are missing playbacks on Kodi" % len(kodiShowsUpdate['shows']))
            for s in ["%s" % self.__getShowAsString(s, short=True) for s in kodiShowsUpdate['shows']]:
                logger.debug("[Episodes Sync] Episodes updated: %s" % s)

            episodes = []
            for show in kodiShowsUpdate['shows']:
                for season in show['seasons']:
                    for episode in season['episodes']:
                        episodes.append({'episodeid': episode['ids']['episodeid'], 'progress': episode['progress'], 'runtime': episode['runtime']})

            # need to calculate the progress in int from progress in percent from Trakt
            # split episode list into chunks of 50
            chunksize = 50
            chunked_episodes = utilities.chunks([{"jsonrpc": "2.0", "id": i, "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid":episodes[i]['episodeid'], "resume": {"position": episodes[i]['runtime'] / 100.0 * episodes[i]['progress'], "total": episodes[i]['runtime']}}} for i in range(len(episodes))], chunksize)
            i = 0
            x = float(len(episodes))
            for chunk in chunked_episodes:
                if self.sync.IsCanceled():
                    return
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32130) % ((i) * chunksize if (i) * chunksize < x else x, x))

                kodiUtilities.kodiJsonRequest(chunk)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32131) % len(episodes))

    def __syncShowsRatings(self, traktShows, kodiShows, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_sync_ratings') and traktShows and not self.sync.IsCanceled():
            updateKodiTraktShows = copy.deepcopy(traktShows)
            updateKodiKodiShows = copy.deepcopy(kodiShows)

            traktShowsToUpdate = self.__compareShows(updateKodiKodiShows, updateKodiTraktShows, rating=True)
            if len(traktShowsToUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32181))
                logger.debug("[Episodes Sync] Trakt show ratings are up to date.")
            else:
                logger.debug("[Episodes Sync] %i show(s) will have show ratings added on Trakt" % len(traktShowsToUpdate['shows']))

                self.sync.UpdateProgress(fromPercent, line1='', line2=kodiUtilities.getString(32182) % len(traktShowsToUpdate['shows']))

                self.sync.traktapi.addRating(traktShowsToUpdate)

            # needs to be restricted, because we can't add a rating to an episode which is not in our Kodi collection
            kodiShowsUpdate = self.__compareShows(updateKodiTraktShows, updateKodiKodiShows, rating=True, restrict = True)

            if len(kodiShowsUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32176))
                logger.debug("[Episodes Sync] Kodi show ratings are up to date.")
            else:
                logger.debug("[Episodes Sync] %i show(s) will have show ratings added in Kodi" % len(kodiShowsUpdate['shows']))

                shows = []
                for show in kodiShowsUpdate['shows']:
                    shows.append({'tvshowid': show['tvshowid'], 'rating': show['rating']})

                # split episode list into chunks of 50
                chunksize = 50
                chunked_episodes = utilities.chunks([{"jsonrpc": "2.0", "id": i, "method": "VideoLibrary.SetTVShowDetails",
                                        "params": {"tvshowid": shows[i]['tvshowid'],
                                                   "userrating": shows[i]['rating']}} for i in range(len(shows))],
                                        chunksize)
                i = 0
                x = float(len(shows))
                for chunk in chunked_episodes:
                    if self.sync.IsCanceled():
                        return
                    i += 1
                    y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                    self.sync.UpdateProgress(int(y), line1='', line2=kodiUtilities.getString(32177) % ((i) * chunksize if (i) * chunksize < x else x, x))

                    kodiUtilities.kodiJsonRequest(chunk)

                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32178) % len(shows))


    def __syncEpisodeRatings(self, traktShows, kodiShows, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_sync_ratings') and traktShows and not self.sync.IsCanceled():
            updateKodiTraktShows = copy.deepcopy(traktShows)
            updateKodiKodiShows = copy.deepcopy(kodiShows)

            traktShowsToUpdate = self.__compareEpisodes(updateKodiKodiShows, updateKodiTraktShows, rating=True)
            if len(traktShowsToUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32181))
                logger.debug("[Episodes Sync] Trakt episode ratings are up to date.")
            else:
                logger.debug("[Episodes Sync] %i show(s) will have episode ratings added on Trakt" % len(traktShowsToUpdate['shows']))

                self.sync.UpdateProgress(fromPercent, line1='', line2=kodiUtilities.getString(32182) % len(traktShowsToUpdate['shows']))
                self.sync.traktapi.addRating(traktShowsToUpdate)


            kodiShowsUpdate = self.__compareEpisodes(updateKodiTraktShows, updateKodiKodiShows, restrict=True, rating=True)
            if len(kodiShowsUpdate['shows']) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32173))
                logger.debug("[Episodes Sync] Kodi episode ratings are up to date.")
            else:
                logger.debug("[Episodes Sync] %i show(s) will have episode ratings added in Kodi" % len(kodiShowsUpdate['shows']))
                for s in ["%s" % self.__getShowAsString(s, short=True) for s in kodiShowsUpdate['shows']]:
                    logger.debug("[Episodes Sync] Episodes updated: %s" % s)

                episodes = []
                for show in kodiShowsUpdate['shows']:
                    for season in show['seasons']:
                        for episode in season['episodes']:
                            episodes.append({'episodeid': episode['ids']['episodeid'], 'rating': episode['rating']})

                # split episode list into chunks of 50
                chunksize = 50
                chunked_episodes = utilities.chunks([{"jsonrpc": "2.0", "id": i, "method": "VideoLibrary.SetEpisodeDetails",
                                        "params": {"episodeid": episodes[i]['episodeid'],
                                                   "userrating": episodes[i]['rating']}} for i in range(len(episodes))],
                                        chunksize)
                i = 0
                x = float(len(episodes))
                for chunk in chunked_episodes:
                    if self.sync.IsCanceled():
                        return
                    i += 1
                    y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                    self.sync.UpdateProgress(int(y), line1='', line2=kodiUtilities.getString(32174) % ((i) * chunksize if (i) * chunksize < x else x, x))

                    kodiUtilities.kodiJsonRequest(chunk)

                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32175) % len(episodes))

    def __countEpisodes(self, shows, collection=True):
        count = 0
        if 'shows' in shows:
            shows = shows['shows']
        for show in shows:
            for seasonKey in show['seasons']:
                if seasonKey is not None and 'episodes' in seasonKey:
                    for episodeKey in seasonKey['episodes']:
                        if episodeKey is not None:
                            if 'collected' in episodeKey and not episodeKey['collected'] == collection:
                                continue
                            if 'number' in episodeKey and episodeKey['number']:
                                count += 1
        return count

    def __getShowAsString(self, show, short=False):
        p = []
        if 'seasons' in show:
            for season in show['seasons']:
                s = ""
                if short:
                    s = ", ".join(["S%02dE%02d" % (season['number'], i['number']) for i in season['episodes']])
                else:
                    episodes = ", ".join([str(i) for i in show['shows']['seasons'][season]])
                    s = "Season: %d, Episodes: %s" % (season, episodes)
                p.append(s)
        else:
            p = ["All"]
        if 'tvdb' in show['ids']:
            return "%s [tvdb: %s] - %s" % (show['title'], show['ids']['tvdb'], ", ".join(p))
        else:
            return "%s [tvdb: No id] - %s" % (show['title'], ", ".join(p))

    def __getEpisodes(self, seasons):
        data = {}
        for season in seasons:
            episodes = {}
            for episode in season['episodes']:
                episodes[episode['number']] = episode
            data[season['number']] = episodes

        return data

    def __compareShows(self, shows_col1, shows_col2, rating=False, restrict=False):
        shows = []
        for show_col1 in shows_col1['shows']:
            if show_col1:
                show_col2 = utilities.findMediaObject(show_col1, shows_col2['shows'])
                # logger.debug("show_col1 %s" % show_col1)
                # logger.debug("show_col2 %s" % show_col2)

                if show_col2:
                    show = {'title': show_col1['title'], 'ids': {}, 'year': show_col1['year']}
                    if 'tvdb' in show_col1['ids']:
                        show['ids'] = {'tvdb': show_col1['ids']['tvdb']}
                    if 'imdb' in show_col2 and show_col2['imdb']:
                        show['ids']['imdb'] = show_col2['imdb']
                    if 'tvshowid' in show_col2:
                        show['tvshowid'] = show_col2['tvshowid']

                    if rating and 'rating' in show_col1 and show_col1['rating'] <> 0 and ('rating' not in show_col2 or show_col2['rating'] == 0):
                        show['rating'] = show_col1['rating']
                        shows.append(show)
                    elif not rating:
                        shows.append(show)
                else:
                    if not restrict:
                        show = {'title': show_col1['title'], 'ids': {}, 'year': show_col1['year']}
                        if 'tvdb' in show_col1['ids']:
                            show['ids'] = {'tvdb': show_col1['ids']['tvdb']}

                        if rating and 'rating' in show_col1 and show_col1['rating'] <> 0:
                            show['rating'] = show_col1['rating']
                            shows.append(show)
                        elif not rating:
                            shows.append(show)

        result = {'shows': shows}
        return result


    # always return shows_col1 if you have enrich it, but don't return shows_col2
    def __compareEpisodes(self, shows_col1, shows_col2, watched=False, restrict=False, collected=False, playback=False, rating=False):
        shows = []
        for show_col1 in shows_col1['shows']:
            if show_col1:
                show_col2 = utilities.findMediaObject(show_col1, shows_col2['shows'])
                # logger.debug("show_col1 %s" % show_col1)
                # logger.debug("show_col2 %s" % show_col2)

                if show_col2:
                    season_diff = {}
                    # format the data to be easy to compare Trakt and KODI data
                    season_col1 = self.__getEpisodes(show_col1['seasons'])
                    season_col2 = self.__getEpisodes(show_col2['seasons'])
                    for season in season_col1:
                        a = season_col1[season]
                        if season in season_col2:
                            b = season_col2[season]
                            diff = list(set(a).difference(set(b)))
                            if playback:
                                t = list(set(a).intersection(set(b)))
                                if len(t) > 0:
                                    eps = {}
                                    for ep in t:
                                        eps[ep] = a[ep]
                                        if 'episodeid' in season_col2[season][ep]['ids']:
                                            if 'ids' in eps:
                                                eps[ep]['ids']['episodeid'] = season_col2[season][ep]['ids']['episodeid']
                                            else:
                                                eps[ep]['ids'] = {'episodeid': season_col2[season][ep]['ids']['episodeid']}
                                        eps[ep]['runtime'] = season_col2[season][ep]['runtime']
                                    season_diff[season] = eps
                            elif rating:
                                t = list(set(a).intersection(set(b)))
                                if len(t) > 0:
                                    eps = {}
                                    for ep in t:
                                        if 'rating' in a[ep] and a[ep]['rating'] <> 0 and season_col2[season][ep]['rating'] == 0:
                                            eps[ep] = a[ep]
                                            if 'episodeid' in season_col2[season][ep]['ids']:
                                                if 'ids' in eps:
                                                    eps[ep]['ids']['episodeid'] = season_col2[season][ep]['ids']['episodeid']
                                                else:
                                                    eps[ep]['ids'] = {'episodeid': season_col2[season][ep]['ids']['episodeid']}
                                    if len(eps) > 0:
                                        season_diff[season] = eps
                            elif len(diff) > 0:
                                if restrict:
                                    # get all the episodes that we have in Kodi, watched or not - update kodi
                                    collectedShow = utilities.findMediaObject(show_col1, collected['shows'])
                                    # logger.debug("collected %s" % collectedShow)
                                    collectedSeasons = self.__getEpisodes(collectedShow['seasons'])
                                    t = list(set(collectedSeasons[season]).intersection(set(diff)))
                                    if len(t) > 0:
                                        eps = {}
                                        for ep in t:
                                            eps[ep] = a[ep]
                                            if 'episodeid' in collectedSeasons[season][ep]['ids']:
                                                if 'ids' in eps:
                                                    eps[ep]['ids']['episodeid'] = collectedSeasons[season][ep]['ids']['episodeid']
                                                else:
                                                    eps[ep]['ids'] = {'episodeid': collectedSeasons[season][ep]['ids']['episodeid']}
                                        season_diff[season] = eps
                                else:
                                    eps = {}
                                    for ep in diff:
                                        eps[ep] = a[ep]
                                    if len(eps) > 0:
                                        season_diff[season] = eps
                        else:
                            if not restrict and not rating:
                                if len(a) > 0:
                                    season_diff[season] = a
                    # logger.debug("season_diff %s" % season_diff)
                    if len(season_diff) > 0:
                        # logger.debug("Season_diff")
                        show = {'title': show_col1['title'], 'ids': {}, 'year': show_col1['year'], 'seasons': []}
                        if 'tvdb' in show_col1['ids']:
                            show['ids'] = {'tvdb': show_col1['ids']['tvdb']}
                        for seasonKey in season_diff:
                            episodes = []
                            for episodeKey in season_diff[seasonKey]:
                                episodes.append(season_diff[seasonKey][episodeKey])
                            show['seasons'].append({'number': seasonKey, 'episodes': episodes})
                        if 'imdb' in show_col2 and show_col2['imdb']:
                            show['ids']['imdb'] = show_col2['imdb']
                        if 'tvshowid' in show_col2:
                            show['tvshowid'] = show_col2['tvshowid']
                        # logger.debug("show %s" % show)
                        shows.append(show)
                else:
                    if not restrict:
                        if self.__countEpisodes([show_col1]) > 0:
                            show = {'title': show_col1['title'], 'ids': {}, 'year': show_col1['year'], 'seasons': []}
                            if 'tvdb' in show_col1['ids']:
                                show['ids'] = {'tvdb': show_col1['ids']['tvdb']}
                            for seasonKey in show_col1['seasons']:
                                episodes = []
                                for episodeKey in seasonKey['episodes']:
                                    if watched and (episodeKey['watched'] == 1):
                                        episodes.append(episodeKey)
                                    elif rating and episodeKey['rating'] <> 0:
                                        episodes.append(episodeKey)
                                    elif not watched and not rating:
                                        episodes.append(episodeKey)
                                if len(episodes) > 0:
                                    show['seasons'].append({'number': seasonKey['number'], 'episodes': episodes})

                            if 'tvshowid' in show_col1:
                                del(show_col1['tvshowid'])
                            if self.__countEpisodes([show]) > 0:
                                shows.append(show)
        result = {'shows': shows}
        return result


    @staticmethod
    def sanitizeShows(shows):
        # do not remove watched_at and collected_at may cause problems between the 4 sync types (would probably have to deepcopy etc)
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
