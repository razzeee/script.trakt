import copy
import logging
from typing import Any

from resources.lib import kodiUtilities, utilities

logger = logging.getLogger(__name__)


class SyncMovies:
    sync: Any

    def __init__(self, sync: Any, progress: Any) -> None:
        self.sync = sync
        if self.sync.show_notification:
            kodiUtilities.notification(
                f"{kodiUtilities.getString(32045)} {kodiUtilities.getString(32046)}",
                kodiUtilities.getString(32061),
            )  # Sync started
        if sync.show_progress and not sync.run_silent:
            progress.create(
                f"{kodiUtilities.getString(32045)} {kodiUtilities.getString(32046)}",
                "",
            )

        kodiMovies = self.__kodiLoadMovies()
        if not isinstance(kodiMovies, list) and not kodiMovies:
            logger.debug("[Movies Sync] Kodi movie list is empty, aborting movie Sync.")
            if sync.show_progress and not sync.run_silent:
                progress.close()
            return
        try:
            traktMovies = self.__traktLoadMovies()
        except Exception:  # noqa: BLE001 - preserve the existing broad failure boundary
            logger.debug(
                "[Movies Sync] Error getting Trakt.tv movie list, aborting movie Sync."
            )
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

        if self.sync.show_progress and not self.sync.run_silent:
            self.sync.UpdateProgress(
                100, line1=kodiUtilities.getString(32066), line2=" ", line3=" "
            )
            progress.close()

        if self.sync.show_notification:
            kodiUtilities.notification(
                f"{kodiUtilities.getString(32045)} {kodiUtilities.getString(32046)}",
                kodiUtilities.getString(32062),
            )  # Sync complete

        logger.debug(
            f"[Movies Sync] Movies on Trakt.tv ({len(traktMovies):d}), movies in Kodi ({len(kodiMovies):d})."
        )
        logger.debug("[Movies Sync] Complete.")

    def __kodiLoadMovies(self) -> list[dict] | None:
        self.sync.UpdateProgress(1, line2=kodiUtilities.getString(32079))

        logger.debug("[Movies Sync] Getting movie data from Kodi")
        data = kodiUtilities.kodiJsonRequest(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "VideoLibrary.GetMovies",
                "params": {
                    "properties": [
                        "title",
                        "imdbnumber",
                        "uniqueid",
                        "year",
                        "playcount",
                        "lastplayed",
                        "file",
                        "dateadded",
                        "runtime",
                        "userrating",
                    ]
                },
            }
        )
        if data["limits"]["total"] == 0:
            logger.debug("[Movies Sync] Kodi JSON request was empty.")
            return

        kodi_movies = kodiUtilities.kodiRpcToTraktMediaObjects(data)

        self.sync.UpdateProgress(10, line2=kodiUtilities.getString(32080))

        return kodi_movies

    def __traktLoadMovies(self) -> list[dict]:
        self.sync.UpdateProgress(
            10,
            line1=kodiUtilities.getString(32079),
            line2=kodiUtilities.getString(32081),
        )

        logger.debug("[Movies Sync] Getting movie collection from Trakt.tv")

        traktMovies = {}
        traktMovies = self.sync.traktapi.getMoviesCollected(traktMovies)

        self.sync.UpdateProgress(17, line2=kodiUtilities.getString(32082))
        traktMovies = self.sync.traktapi.getMoviesWatched(traktMovies)

        if kodiUtilities.getSettingAsBool("trakt_sync_ratings"):
            traktMovies = self.sync.traktapi.getMoviesRated(traktMovies)

        traktMovies = list(traktMovies.items())

        self.sync.UpdateProgress(24, line2=kodiUtilities.getString(32083))
        movies = []
        for _, movie in traktMovies:
            movie = movie.to_dict()

            movies.append(movie)

        return movies

    def __traktLoadMoviesPlaybackProgress(
        self, fromPercent: int, toPercent: int
    ) -> dict | bool:
        if (
            kodiUtilities.getSettingAsBool("trakt_movie_playback")
            and not self.sync.IsCanceled()
        ):
            self.sync.UpdateProgress(fromPercent, line2=kodiUtilities.getString(32122))

            logger.debug("[Movies Sync] Getting playback progress from Trakt.tv")
            try:
                traktProgressMovies = self.sync.traktapi.getMoviePlaybackProgress()
            except Exception:  # noqa: BLE001 - preserve the existing broad failure boundary
                logger.debug(
                    "[Movies Sync] Invalid Trakt.tv playback progress list, possible error getting data from Trakt, aborting Trakt.tv playback update."
                )
                return False

            x = float(len(traktProgressMovies))
            moviesProgress = {"movies": []}
            for i, (movie) in enumerate(traktProgressMovies, start=1):
                y = ((i / x) * (toPercent - fromPercent)) + fromPercent
                self.sync.UpdateProgress(
                    int(y), line2=kodiUtilities.getString(32123) % (i, x)
                )

                # will keep the data in python structures - just like the KODI response
                movie = movie.to_dict()

                moviesProgress["movies"].append(movie)

            self.sync.UpdateProgress(toPercent, line2=kodiUtilities.getString(32124))

            return moviesProgress

    def __addMoviesToTraktCollection(
        self,
        kodiMovies: list[dict],
        traktMovies: list[dict],
        fromPercent: int,
        toPercent: int,
    ) -> None:
        if (
            kodiUtilities.getSettingAsBool("add_movies_to_trakt")
            and not self.sync.IsCanceled()
        ):
            addTraktMovies = copy.deepcopy(traktMovies)
            addKodiMovies = copy.deepcopy(kodiMovies)

            traktMoviesToAdd = utilities.compareMovies(
                addKodiMovies,
                addTraktMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
            )
            utilities.sanitizeMovies(traktMoviesToAdd)
            logger.debug(
                f"[Movies Sync] Compared movies, found {len(traktMoviesToAdd)} to add."
            )

            if len(traktMoviesToAdd) == 0:
                self.sync.UpdateProgress(
                    toPercent, line2=kodiUtilities.getString(32084)
                )
                logger.debug("[Movies Sync] Trakt.tv movie collection is up to date.")
                return

            titles = ", ".join(["{}".format(m["title"]) for m in traktMoviesToAdd])
            logger.debug(
                f"[Movies Sync] {len(traktMoviesToAdd):d} movie(s) will be added to Trakt.tv collection."
            )
            logger.debug(f"[Movies Sync] Movies to add : {titles}")

            self.sync.UpdateProgress(
                fromPercent,
                line2=kodiUtilities.getString(32063) % len(traktMoviesToAdd),
            )

            moviesToAdd = {"movies": traktMoviesToAdd}
            # logger.debug("Movies to add: %s" % moviesToAdd)
            try:
                self.sync.traktapi.addToCollection(moviesToAdd)
            except Exception as ex:  # noqa: BLE001 - preserve the existing broad failure boundary
                message = utilities.createError(ex)
                logging.fatal(message)

            self.sync.UpdateProgress(
                toPercent, line2=kodiUtilities.getString(32085) % len(traktMoviesToAdd)
            )

    def __deleteMoviesFromTraktCollection(
        self,
        traktMovies: list[dict],
        kodiMovies: list[dict],
        fromPercent: int,
        toPercent: int,
    ) -> None:
        if (
            kodiUtilities.getSettingAsBool("clean_trakt_movies")
            and not self.sync.IsCanceled()
        ):
            removeTraktMovies = copy.deepcopy(traktMovies)
            removeKodiMovies = copy.deepcopy(kodiMovies)

            logger.debug("[Movies Sync] Starting to remove.")
            traktMoviesToRemove = utilities.compareMovies(
                removeTraktMovies,
                removeKodiMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
            )
            utilities.sanitizeMovies(traktMoviesToRemove)
            logger.debug(
                f"[Movies Sync] Compared movies, found {len(traktMoviesToRemove)} to remove."
            )

            if len(traktMoviesToRemove) == 0:
                self.sync.UpdateProgress(
                    toPercent, line2=kodiUtilities.getString(32091)
                )
                logger.debug(
                    "[Movies Sync] Trakt.tv movie collection is clean, no movies to remove."
                )
                return

            titles = ", ".join(["{}".format(m["title"]) for m in traktMoviesToRemove])
            logger.debug(
                f"[Movies Sync] {len(traktMoviesToRemove):d} movie(s) will be removed from Trakt.tv collection."
            )
            logger.debug(f"[Movies Sync] Movies removed: {titles}")

            self.sync.UpdateProgress(
                fromPercent,
                line2=kodiUtilities.getString(32076) % len(traktMoviesToRemove),
            )

            moviesToRemove = {"movies": traktMoviesToRemove}
            try:
                self.sync.traktapi.removeFromCollection(moviesToRemove)
            except Exception as ex:  # noqa: BLE001 - preserve the existing broad failure boundary
                message = utilities.createError(ex)
                logging.fatal(message)

            self.sync.UpdateProgress(
                toPercent,
                line2=kodiUtilities.getString(32092) % len(traktMoviesToRemove),
            )

    def __addMoviesToTraktWatched(
        self,
        kodiMovies: list[dict],
        traktMovies: list[dict],
        fromPercent: int,
        toPercent: int,
    ) -> None:
        if (
            kodiUtilities.getSettingAsBool("trakt_movie_playcount")
            and not self.sync.IsCanceled()
        ):
            updateTraktTraktMovies = copy.deepcopy(traktMovies)
            updateTraktKodiMovies = copy.deepcopy(kodiMovies)

            traktMoviesToUpdate = utilities.compareMovies(
                updateTraktKodiMovies,
                updateTraktTraktMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
                watched=True,
            )
            utilities.sanitizeMovies(traktMoviesToUpdate)

            if len(traktMoviesToUpdate) == 0:
                self.sync.UpdateProgress(
                    toPercent, line2=kodiUtilities.getString(32086)
                )
                logger.debug("[Movies Sync] Trakt.tv movie playcount is up to date")
                return

            titles = ", ".join(["{}".format(m["title"]) for m in traktMoviesToUpdate])
            logger.debug(
                f"[Movies Sync] {len(traktMoviesToUpdate):d} movie(s) playcount will be updated on Trakt.tv"
            )
            logger.debug(f"[Movies Sync] Movies updated: {titles}")

            self.sync.UpdateProgress(
                fromPercent,
                line2=kodiUtilities.getString(32064) % len(traktMoviesToUpdate),
            )
            # Send request to update playcounts on Trakt.tv
            chunksize = 200
            chunked_movies = utilities.chunks(
                [movie for movie in traktMoviesToUpdate], chunksize
            )
            errorcount = 0
            x = float(len(traktMoviesToUpdate))
            for i, (chunk) in enumerate(chunked_movies, start=1):
                if self.sync.IsCanceled():
                    return
                y = ((i / x) * (toPercent - fromPercent)) + fromPercent
                self.sync.UpdateProgress(
                    int(y),
                    line2=kodiUtilities.getString(32093) % (min(x, i * chunksize), x),
                )

                params = {"movies": chunk}
                # logger.debug("moviechunk: %s" % params)
                try:
                    self.sync.traktapi.addToHistory(params)
                except Exception as ex:  # noqa: BLE001 - preserve the existing broad failure boundary
                    message = utilities.createError(ex)
                    logging.fatal(message)
                    errorcount += 1

            logger.debug(f"[Movies Sync] Movies updated: {errorcount:d} error(s)")
            self.sync.UpdateProgress(
                toPercent,
                line2=kodiUtilities.getString(32087) % len(traktMoviesToUpdate),
            )

    def __addMoviesToKodiWatched(
        self,
        traktMovies: list[dict],
        kodiMovies: list[dict],
        fromPercent: int,
        toPercent: int,
    ) -> None:
        if (
            kodiUtilities.getSettingAsBool("kodi_movie_playcount")
            and not self.sync.IsCanceled()
        ):
            updateKodiTraktMovies = copy.deepcopy(traktMovies)
            updateKodiKodiMovies = copy.deepcopy(kodiMovies)

            kodiMoviesToUpdate = utilities.compareMovies(
                updateKodiTraktMovies,
                updateKodiKodiMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
                watched=True,
                restrict=True,
            )

            if len(kodiMoviesToUpdate) == 0:
                self.sync.UpdateProgress(
                    toPercent, line2=kodiUtilities.getString(32088)
                )
                logger.debug("[Movies Sync] Kodi movie playcount is up to date.")
                return

            titles = ", ".join(["{}".format(m["title"]) for m in kodiMoviesToUpdate])
            logger.debug(
                f"[Movies Sync] {len(kodiMoviesToUpdate):d} movie(s) playcount will be updated in Kodi"
            )
            logger.debug(f"[Movies Sync] Movies to add: {titles}")

            self.sync.UpdateProgress(
                fromPercent,
                line2=kodiUtilities.getString(32065) % len(kodiMoviesToUpdate),
            )

            # split movie list into chunks of 50
            chunksize = 50
            chunked_movies = utilities.chunks(
                [
                    {
                        "jsonrpc": "2.0",
                        "method": "VideoLibrary.SetMovieDetails",
                        "params": {
                            "movieid": kodiMoviesToUpdate[i]["movieid"],
                            "playcount": kodiMoviesToUpdate[i]["plays"],
                            "lastplayed": utilities.convertUtcToDateTime(
                                kodiMoviesToUpdate[i]["last_watched_at"]
                            ),
                        },
                        "id": i,
                    }
                    for i in range(len(kodiMoviesToUpdate))
                ],
                chunksize,
            )
            x = float(len(kodiMoviesToUpdate))
            for i, (chunk) in enumerate(chunked_movies, start=1):
                if self.sync.IsCanceled():
                    return
                y = ((i / x) * (toPercent - fromPercent)) + fromPercent
                self.sync.UpdateProgress(
                    int(y),
                    line2=kodiUtilities.getString(32089) % (min(x, i * chunksize), x),
                )

                kodiUtilities.kodiJsonRequest(chunk)

            self.sync.UpdateProgress(
                toPercent,
                line2=kodiUtilities.getString(32090) % len(kodiMoviesToUpdate),
            )

    def __addMovieProgressToKodi(
        self,
        traktMovies: dict,
        kodiMovies: list[dict],
        fromPercent: int,
        toPercent: int,
    ) -> None:
        if (
            kodiUtilities.getSettingAsBool("trakt_movie_playback")
            and traktMovies
            and not self.sync.IsCanceled()
        ):
            updateKodiTraktMovies = copy.deepcopy(traktMovies)
            updateKodiKodiMovies = copy.deepcopy(kodiMovies)

            kodiMoviesToUpdate = utilities.compareMovies(
                updateKodiTraktMovies["movies"],
                updateKodiKodiMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
                restrict=True,
                playback=True,
            )
            if len(kodiMoviesToUpdate) == 0:
                self.sync.UpdateProgress(
                    toPercent, line1="", line2=kodiUtilities.getString(32125)
                )
                logger.debug("[Movies Sync] Kodi movie progress is up to date.")
                return

            logger.debug(
                f"[Movies Sync] {len(kodiMoviesToUpdate):d} movie(s) progress will be updated in Kodi"
            )

            self.sync.UpdateProgress(
                fromPercent,
                line1="",
                line2=kodiUtilities.getString(32126) % len(kodiMoviesToUpdate),
            )
            # If library item doesn't have a runtime set get it from
            # Trakt to avoid later using 0 in runtime * progress_pct.
            for movie in kodiMoviesToUpdate:
                if not movie["runtime"]:
                    movie["runtime"] = (
                        self.sync.traktapi.getMovieSummary(
                            movie["ids"]["trakt"], extended="full"
                        ).runtime
                        * 60
                    )
            # need to calculate the progress in int from progress in percent from Trakt
            # split movie list into chunks of 50
            chunksize = 50
            chunked_movies = utilities.chunks(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": i,
                        "method": "VideoLibrary.SetMovieDetails",
                        "params": {
                            "movieid": kodiMoviesToUpdate[i]["movieid"],
                            "resume": {
                                "position": kodiMoviesToUpdate[i]["runtime"]
                                / 100.0
                                * kodiMoviesToUpdate[i]["progress"],
                                "total": kodiMoviesToUpdate[i]["runtime"],
                            },
                        },
                    }
                    for i in range(len(kodiMoviesToUpdate))
                    if kodiMoviesToUpdate[i]["runtime"] > 0
                ],
                chunksize,
            )
            x = float(len(kodiMoviesToUpdate))
            for i, (chunk) in enumerate(chunked_movies, start=1):
                if self.sync.IsCanceled():
                    return
                y = ((i / x) * (toPercent - fromPercent)) + fromPercent
                self.sync.UpdateProgress(
                    int(y),
                    line2=kodiUtilities.getString(32127) % (min(x, i * chunksize), x),
                )
                kodiUtilities.kodiJsonRequest(chunk)

            self.sync.UpdateProgress(
                toPercent,
                line2=kodiUtilities.getString(32128) % len(kodiMoviesToUpdate),
            )

    def __syncMovieRatings(
        self,
        traktMovies: list[dict],
        kodiMovies: list[dict],
        fromPercent: int,
        toPercent: int,
    ) -> None:
        if (
            kodiUtilities.getSettingAsBool("trakt_sync_ratings")
            and traktMovies
            and not self.sync.IsCanceled()
        ):
            updateKodiTraktMovies = copy.deepcopy(traktMovies)
            updateKodiKodiMovies = copy.deepcopy(kodiMovies)

            traktMoviesToUpdate = utilities.compareMovies(
                updateKodiKodiMovies,
                updateKodiTraktMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
                rating=True,
            )
            if len(traktMoviesToUpdate) == 0:
                self.sync.UpdateProgress(
                    toPercent, line1="", line2=kodiUtilities.getString(32179)
                )
                logger.debug("[Movies Sync] Trakt movie ratings are up to date.")
            else:
                logger.debug(
                    f"[Movies Sync] {len(traktMoviesToUpdate):d} movie(s) ratings will be updated on Trakt"
                )

                self.sync.UpdateProgress(
                    fromPercent,
                    line1="",
                    line2=kodiUtilities.getString(32180) % len(traktMoviesToUpdate),
                )

                moviesRatings = {"movies": traktMoviesToUpdate}

                self.sync.traktapi.addRating(moviesRatings)

            kodiMoviesToUpdate = utilities.compareMovies(
                updateKodiTraktMovies,
                updateKodiKodiMovies,
                kodiUtilities.getSettingAsBool("scrobble_fallback"),
                restrict=True,
                rating=True,
            )
            if len(kodiMoviesToUpdate) == 0:
                self.sync.UpdateProgress(
                    toPercent, line1="", line2=kodiUtilities.getString(32169)
                )
                logger.debug("[Movies Sync] Kodi movie ratings are up to date.")
            else:
                logger.debug(
                    f"[Movies Sync] {len(kodiMoviesToUpdate):d} movie(s) ratings will be updated in Kodi"
                )

                self.sync.UpdateProgress(
                    fromPercent,
                    line1="",
                    line2=kodiUtilities.getString(32170) % len(kodiMoviesToUpdate),
                )
                # split movie list into chunks of 50
                chunksize = 50
                chunked_movies = utilities.chunks(
                    [
                        {
                            "jsonrpc": "2.0",
                            "id": i,
                            "method": "VideoLibrary.SetMovieDetails",
                            "params": {
                                "movieid": kodiMoviesToUpdate[i]["movieid"],
                                "userrating": kodiMoviesToUpdate[i]["rating"],
                            },
                        }
                        for i in range(len(kodiMoviesToUpdate))
                    ],
                    chunksize,
                )
                x = float(len(kodiMoviesToUpdate))
                for i, (chunk) in enumerate(chunked_movies, start=1):
                    if self.sync.IsCanceled():
                        return
                    y = ((i / x) * (toPercent - fromPercent)) + fromPercent
                    self.sync.UpdateProgress(
                        int(y),
                        line2=kodiUtilities.getString(32171)
                        % (min(x, i * chunksize), x),
                    )
                    kodiUtilities.kodiJsonRequest(chunk)

                self.sync.UpdateProgress(
                    toPercent,
                    line2=kodiUtilities.getString(32172) % len(kodiMoviesToUpdate),
                )
