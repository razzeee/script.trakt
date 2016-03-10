# -*- coding: utf-8 -*-

import copy
import utilities
import kodiUtilities
import logging
from kodiUtilities import notification

logger = logging.getLogger(__name__)

class SyncMovies():
    def __init__(self, sync, progress):
        self.sync = sync
        if not self.sync.show_progress and sync.sync_on_update and sync.notify and self.sync.notify_during_playback:
            notification('%s %s' % (kodiUtilities.getString(32045), kodiUtilities.getString(32046)), kodiUtilities.getString(32061))  # Sync started
        if sync.show_progress and not sync.run_silent:
            progress.create("%s %s" % (kodiUtilities.getString(32045), kodiUtilities.getString(32046)), line1=" ", line2=" ", line3=" ")

        kodiMovies = self.__kodiLoadMovies()
        if not isinstance(kodiMovies, list) and not kodiMovies:
            logger.debug("[Movies Sync] Kodi movie list is empty, aborting movie Sync.")
            if sync.show_progress and not sync.run_silent:
                progress.close()
            return
        try:
            traktMovies = self.__traktLoadMovies()
        except Exception:
            logger.debug("[Movies Sync] Error getting Trakt.tv movie list, aborting movie Sync.")
            if sync.show_progress and not sync.run_silent:
                progress.close()
            return

        traktMoviesProgress = self.__traktLoadMoviesPlaybackProgress(25, 36)

        self.__addMoviesToTraktCollection(kodiMovies, traktMovies, 37, 47)

        self.__deleteMoviesFromTraktCollection(traktMovies, kodiMovies, 48, 58)

        self.__addMoviesToTraktWatched(kodiMovies, traktMovies, 59, 69)

        self.__addMoviesToKodiWatched(traktMovies, kodiMovies, 70, 80)

        self.__addMovieProgressToKodi(traktMoviesProgress, kodiMovies, 81, 91)

        self.__syncMovieRatings(traktMovies, kodiMovies, 92, 99)

        if sync.show_progress and not sync.run_silent:
            self.sync.UpdateProgress(100, line1=kodiUtilities.getString(32066), line2=" ", line3=" ")
            progress.close()

        if not sync.show_progress and sync.sync_on_update and sync.notify and sync.notify_during_playback:
            notification('%s %s' % (kodiUtilities.getString(32045), kodiUtilities.getString(32046)), kodiUtilities.getString(32062))  # Sync complete

        logger.debug("[Movies Sync] Movies on Trakt.tv (%d), movies in Kodi (%d)." % (len(traktMovies), len(kodiMovies)))
        logger.debug("[Movies Sync] Complete.")

    def __compareMovies(self, movies_col1, movies_col2, watched=False, restrict=False, playback=False, rating=False):
        movies = []

        for movie_col1 in movies_col1:
            if movie_col1:
                movie_col2 = utilities.findMediaObject(movie_col1, movies_col2)
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
                        if 'rating' in movie_col1 and movie_col1['rating'] <> 0 and ('rating' not in movie_col2 or movie_col2['rating'] == 0):
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
                            elif rating and movie_col1['rating'] <> 0:
                                movies.append(movie_col1)
                            elif not watched and not rating:

                                movies.append(movie_col1)
        return movies


    ''' begin code for movie sync '''
    def __kodiLoadMovies(self):
        self.sync.UpdateProgress(1, line2=kodiUtilities.getString(32079))

        logger.debug("[Movies Sync] Getting movie data from Kodi")
        data = kodiUtilities.kodiJsonRequest({'jsonrpc': '2.0', 'id': 0, 'method': 'VideoLibrary.GetMovies', 'params': {'properties': ['title', 'imdbnumber', 'year', 'playcount', 'lastplayed', 'file', 'dateadded', 'runtime', 'userrating']}})
        if data['limits']['total'] == 0:
            logger.debug("[Movies Sync] Kodi JSON request was empty.")
            return

        kodi_movies = kodiUtilities.kodiRpcToTraktMediaObjects(data)

        self.sync.UpdateProgress(10, line2=kodiUtilities.getString(32080))

        return kodi_movies

    def __traktLoadMovies(self):
        self.sync.UpdateProgress(10, line1=kodiUtilities.getString(32079), line2=kodiUtilities.getString(32081))

        logger.debug("[Movies Sync] Getting movie collection from Trakt.tv")

        traktMovies = {}
        traktMovies = self.sync.traktapi.getMoviesCollected(traktMovies)

        self.sync.UpdateProgress(17, line2=kodiUtilities.getString(32082))
        traktMovies = self.sync.traktapi.getMoviesWatched(traktMovies)
        traktMovies = self.sync.traktapi.getMoviesRated(traktMovies)
        traktMovies = traktMovies.items()

        self.sync.UpdateProgress(24, line2=kodiUtilities.getString(32083))
        movies = []
        for _, movie in traktMovies:
            movie = movie.to_dict()

            movies.append(movie)

        return movies

    def __traktLoadMoviesPlaybackProgress(self, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_movie_playback') and not self.sync.IsCanceled():
            self.sync.UpdateProgress(fromPercent, line2=kodiUtilities.getString(32122))

            logger.debug('[Movies Sync] Getting playback progress from Trakt.tv')
            try:
                traktProgressMovies = self.sync.traktapi.getMoviePlaybackProgress()
            except Exception:
                logger.debug("[Movies Sync] Invalid Trakt.tv playback progress list, possible error getting data from Trakt, aborting Trakt.tv playback update.")
                return False

            i = 0
            x = float(len(traktProgressMovies))
            moviesProgress = {'movies': []}
            for movie in traktProgressMovies:
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32123) % (i, x))

                # will keep the data in python structures - just like the KODI response
                movie = movie.to_dict()

                moviesProgress['movies'].append(movie)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32124))

            return moviesProgress

    def __addMoviesToTraktCollection(self, kodiMovies, traktMovies, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('add_movies_to_trakt') and not self.sync.IsCanceled():
            addTraktMovies = copy.deepcopy(traktMovies)
            addKodiMovies = copy.deepcopy(kodiMovies)

            traktMoviesToAdd = self.__compareMovies(addKodiMovies, addTraktMovies)
            self.sanitizeMovies(traktMoviesToAdd)
            logger.debug("[Movies Sync] Compared movies, found %s to add." % len(traktMoviesToAdd))

            if len(traktMoviesToAdd) == 0:
                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32084))
                logger.debug("[Movies Sync] Trakt.tv movie collection is up to date.")
                return

            titles = ", ".join(["%s" % (m['title']) for m in traktMoviesToAdd])
            logger.debug("[Movies Sync] %i movie(s) will be added to Trakt.tv collection." % len(traktMoviesToAdd))
            logger.debug("[Movies Sync] Movies to add : %s" % titles)

            self.sync.UpdateProgress(fromPercent, line2=kodiUtilities.getString(32063) % len(traktMoviesToAdd))

            moviesToAdd = {'movies': traktMoviesToAdd}
            # logger.debug("Movies to add: %s" % moviesToAdd)
            try:
                self.sync.traktapi.addToCollection(moviesToAdd)
            except Exception as ex:
                message = utilities.createError(ex)
                logging.fatal(message)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32085) % len(traktMoviesToAdd))

    def __deleteMoviesFromTraktCollection(self, traktMovies, kodiMovies, fromPercent, toPercent):

        if kodiUtilities.getSettingAsBool('clean_trakt_movies') and not self.sync.IsCanceled():
            removeTraktMovies = copy.deepcopy(traktMovies)
            removeKodiMovies = copy.deepcopy(kodiMovies)

            logger.debug("[Movies Sync] Starting to remove.")
            traktMoviesToRemove = self.__compareMovies(removeTraktMovies, removeKodiMovies)
            self.sanitizeMovies(traktMoviesToRemove)
            logger.debug("[Movies Sync] Compared movies, found %s to remove." % len(traktMoviesToRemove))

            if len(traktMoviesToRemove) == 0:
                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32091))
                logger.debug("[Movies Sync] Trakt.tv movie collection is clean, no movies to remove.")
                return

            titles = ", ".join(["%s" % (m['title']) for m in traktMoviesToRemove])
            logger.debug("[Movies Sync] %i movie(s) will be removed from Trakt.tv collection." % len(traktMoviesToRemove))
            logger.debug("[Movies Sync] Movies removed: %s" % titles)

            self.sync.UpdateProgress(fromPercent, line2=kodiUtilities.getString(32076) % len(traktMoviesToRemove))

            moviesToRemove = {'movies': traktMoviesToRemove}
            try:
                self.sync.traktapi.removeFromCollection(moviesToRemove)
            except Exception as ex:
                message = utilities.createError(ex)
                logging.fatal(message)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32092) % len(traktMoviesToRemove))

    def __addMoviesToTraktWatched(self, kodiMovies, traktMovies, fromPercent, toPercent):
        if kodiUtilities.getSettingAsBool('trakt_movie_playcount') and not self.sync.IsCanceled():
            updateTraktTraktMovies = copy.deepcopy(traktMovies)
            updateTraktKodiMovies = copy.deepcopy(kodiMovies)

            traktMoviesToUpdate = self.__compareMovies(updateTraktKodiMovies, updateTraktTraktMovies, watched=True)
            self.sanitizeMovies(traktMoviesToUpdate)

            if len(traktMoviesToUpdate) == 0:
                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32086))
                logger.debug("[Movies Sync] Trakt.tv movie playcount is up to date")
                return

            titles = ", ".join(["%s" % (m['title']) for m in traktMoviesToUpdate])
            logger.debug("[Movies Sync] %i movie(s) playcount will be updated on Trakt.tv" % len(traktMoviesToUpdate))
            logger.debug("[Movies Sync] Movies updated: %s" % titles)

            self.sync.UpdateProgress(fromPercent, line2=kodiUtilities.getString(32064) % len(traktMoviesToUpdate))
            # Send request to update playcounts on Trakt.tv
            chunksize = 200
            chunked_movies = utilities.chunks([movie for movie in traktMoviesToUpdate], chunksize)
            errorcount = 0
            i = 0
            x = float(len(traktMoviesToUpdate))
            for chunk in chunked_movies:
                if self.sync.IsCanceled():
                    return
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32093) % ((i) * chunksize if (i) * chunksize < x else x, x))

                params = {'movies': chunk}
                # logger.debug("moviechunk: %s" % params)
                try:
                    self.sync.traktapi.addToHistory(params)
                except Exception as ex:
                    message = utilities.createError(ex)
                    logging.fatal(message)
                    errorcount += 1

            logger.debug("[Movies Sync] Movies updated: %d error(s)" % errorcount)
            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32087) % len(traktMoviesToUpdate))

    def __addMoviesToKodiWatched(self, traktMovies, kodiMovies, fromPercent, toPercent):

        if kodiUtilities.getSettingAsBool('kodi_movie_playcount') and not self.sync.IsCanceled():
            updateKodiTraktMovies = copy.deepcopy(traktMovies)
            updateKodiKodiMovies = copy.deepcopy(kodiMovies)

            kodiMoviesToUpdate = self.__compareMovies(updateKodiTraktMovies, updateKodiKodiMovies, watched=True, restrict=True)

            if len(kodiMoviesToUpdate) == 0:
                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32088))
                logger.debug("[Movies Sync] Kodi movie playcount is up to date.")
                return

            titles = ", ".join(["%s" % (m['title']) for m in kodiMoviesToUpdate])
            logger.debug("[Movies Sync] %i movie(s) playcount will be updated in Kodi" % len(kodiMoviesToUpdate))
            logger.debug("[Movies Sync] Movies to add: %s" % titles)

            self.sync.UpdateProgress(fromPercent, line2=kodiUtilities.getString(32065) % len(kodiMoviesToUpdate))

            # split movie list into chunks of 50
            chunksize = 50
            chunked_movies = utilities.chunks([{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": kodiMoviesToUpdate[i]['movieid'], "playcount": kodiMoviesToUpdate[i]['plays'], "lastplayed": utilities.convertUtcToDateTime(kodiMoviesToUpdate[i]['last_watched_at'])}, "id": i} for i in range(len(kodiMoviesToUpdate))], chunksize)
            i = 0
            x = float(len(kodiMoviesToUpdate))
            for chunk in chunked_movies:
                if self.sync.IsCanceled():
                    return
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32089) % ((i) * chunksize if (i) * chunksize < x else x, x))

                kodiUtilities.kodiJsonRequest(chunk)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32090) % len(kodiMoviesToUpdate))

    def __addMovieProgressToKodi(self, traktMovies, kodiMovies, fromPercent, toPercent):

        if kodiUtilities.getSettingAsBool('trakt_movie_playback') and traktMovies and not self.sync.IsCanceled():
            updateKodiTraktMovies = copy.deepcopy(traktMovies)
            updateKodiKodiMovies = copy.deepcopy(kodiMovies)

            kodiMoviesToUpdate = self.__compareMovies(updateKodiTraktMovies['movies'], updateKodiKodiMovies, restrict=True, playback=True)
            if len(kodiMoviesToUpdate) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32125))
                logger.debug("[Movies Sync] Kodi movie playbacks are up to date.")
                return

            logger.debug("[Movies Sync] %i movie(s) playbacks will be updated in Kodi" % len(kodiMoviesToUpdate))

            self.sync.UpdateProgress(fromPercent, line1='', line2=kodiUtilities.getString(32126) % len(kodiMoviesToUpdate))
            # need to calculate the progress in int from progress in percent from Trakt
            # split movie list into chunks of 50
            chunksize = 50
            chunked_movies = utilities.chunks([{"jsonrpc": "2.0", "id": i, "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": kodiMoviesToUpdate[i]['movieid'], "resume": {"position": kodiMoviesToUpdate[i]['runtime'] / 100.0 * kodiMoviesToUpdate[i]['progress'], "total": kodiMoviesToUpdate[i]['runtime']}}} for i in range(len(kodiMoviesToUpdate))], chunksize)
            i = 0
            x = float(len(kodiMoviesToUpdate))
            for chunk in chunked_movies:
                if self.sync.IsCanceled():
                    return
                i += 1
                y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32127) % ((i) * chunksize if (i) * chunksize < x else x, x))
                kodiUtilities.kodiJsonRequest(chunk)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32128) % len(kodiMoviesToUpdate))

    def __syncMovieRatings(self, traktMovies, kodiMovies, fromPercent, toPercent):

        if kodiUtilities.getSettingAsBool('trakt_sync_ratings') and traktMovies and not self.sync.IsCanceled():
            updateKodiTraktMovies = copy.deepcopy(traktMovies)
            updateKodiKodiMovies = copy.deepcopy(kodiMovies)

            traktMoviesToUpdate = self.__compareMovies(updateKodiKodiMovies, updateKodiTraktMovies, rating=True)
            if len(traktMoviesToUpdate) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32179))
                logger.debug("[Movies Sync] Trakt movie ratings are up to date.")
            else:
                logger.debug("[Movies Sync] %i movie(s) ratings will be updated on Trakt" % len(traktMoviesToUpdate))

                self.sync.UpdateProgress(fromPercent, line1='', line2=kodiUtilities.getString(32180) % len(traktMoviesToUpdate))

                moviesRatings = {'movies': traktMoviesToUpdate}

                self.sync.traktapi.addRating(moviesRatings)


            kodiMoviesToUpdate = self.__compareMovies(updateKodiTraktMovies, updateKodiKodiMovies, restrict=True, rating=True)
            if len(kodiMoviesToUpdate) == 0:
                self.sync.UpdateProgress(toPercent, line1='', line2=kodiUtilities.getString(32169))
                logger.debug("[Movies Sync] Kodi movie ratings are up to date.")
            else:
                logger.debug("[Movies Sync] %i movie(s) ratings will be updated in Kodi" % len(kodiMoviesToUpdate))

                self.sync.UpdateProgress(fromPercent, line1='', line2=kodiUtilities.getString(32170) % len(kodiMoviesToUpdate))
                # split movie list into chunks of 50
                chunksize = 50
                chunked_movies = utilities.chunks([{"jsonrpc": "2.0", "id": i, "method": "VideoLibrary.SetMovieDetails",
                                                    "params": {"movieid": kodiMoviesToUpdate[i]['movieid'],
                                                               "userrating": kodiMoviesToUpdate[i]['rating']}} for i in range(len(kodiMoviesToUpdate))],
                                                  chunksize)
                i = 0
                x = float(len(kodiMoviesToUpdate))
                for chunk in chunked_movies:
                    if self.sync.IsCanceled():
                        return
                    i += 1
                    y = ((i / x) * (toPercent-fromPercent)) + fromPercent
                    self.sync.UpdateProgress(int(y), line2=kodiUtilities.getString(32171) % ((i) * chunksize if (i) * chunksize < x else x, x))
                    kodiUtilities.kodiJsonRequest(chunk)

                self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32172) % len(kodiMoviesToUpdate))


    @staticmethod
    def sanitizeMovies(movies):
        # do not remove watched_at and collected_at may cause problems between the 4 sync types (would probably have to deepcopy etc)
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
