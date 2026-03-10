# -*- coding: utf-8 -*-
import mock
import sys

# Mocking Kodi modules BEFORE any project imports
sys.modules["xbmc"] = mock.Mock()
sys.modules["xbmcgui"] = mock.Mock()
sys.modules["xbmcaddon"] = mock.Mock()

from resources.lib import syncEpisodes, syncMovies

def mock_get_string_side_effect(x):
    # Handle strings used with % formatting in progress updates
    if x in [32126, 32128, 32130, 32131, 32097, 32102, 32069, 32093, 32089, 32127, 32171, 32174, 32177, 32182]:
        return "string_%d_%%s" % x
    return "string_%d" % x

def test_addEpisodeProgressToKodi_handles_none_runtime():
    sync_mock = mock.Mock()
    se = syncEpisodes.SyncEpisodes.__new__(syncEpisodes.SyncEpisodes)
    se.sync = sync_mock

    summary_mock = mock.Mock()
    summary_mock.runtime = None
    sync_mock.traktapi.getEpisodeSummary.return_value = summary_mock
    sync_mock.IsCanceled.return_value = False

    kodiShowsUpdate = {
        "shows": [
            {
                "title": "Test Show",
                "ids": {"trakt": 123},
                "seasons": [{"number": 1, "episodes": [{"number": 1, "runtime": None, "ids": {"episodeid": 1}, "progress": 50}]}]
            }
        ]
    }
    with mock.patch('resources.lib.kodiUtilities.getSettingAsBool', return_value=True), \
         mock.patch('resources.lib.kodiUtilities.getString', side_effect=mock_get_string_side_effect), \
         mock.patch('resources.lib.utilities.compareEpisodes', return_value=kodiShowsUpdate):
        # Pass a truthy dict for traktShows to enter the block
        se._SyncEpisodes__addEpisodeProgressToKodi({"shows": []}, {}, 0, 100)

def test_addMovieProgressToKodi_handles_none_runtime():
    sync_mock = mock.Mock()
    sm = syncMovies.SyncMovies.__new__(syncMovies.SyncMovies)
    sm.sync = sync_mock

    summary_mock = mock.Mock()
    summary_mock.runtime = None
    sync_mock.traktapi.getMovieSummary.return_value = summary_mock
    sync_mock.IsCanceled.return_value = False

    kodiMoviesToUpdate = [{"movieid": 1, "runtime": None, "ids": {"trakt": 123}, "progress": 50, "title": "Test"}]
    with mock.patch('resources.lib.kodiUtilities.getSettingAsBool', return_value=True), \
         mock.patch('resources.lib.utilities.compareMovies', return_value=kodiMoviesToUpdate), \
         mock.patch('resources.lib.kodiUtilities.getString', side_effect=mock_get_string_side_effect):
        # Pass a truthy dict for traktMovies to enter the block
        sm._SyncMovies__addMovieProgressToKodi({"movies": kodiMoviesToUpdate}, [], 0, 100)

def test_getShowAsString_navigates_correctly():
    sync_mock = mock.Mock()
    se = syncEpisodes.SyncEpisodes.__new__(syncEpisodes.SyncEpisodes)
    se.sync = sync_mock

    show = {
        "title": "Game of Thrones",
        "ids": {"trakt": 121361, "tvdb": 121361},
        "seasons": [
            {
                "number": 1,
                "episodes": [{"number": 1, "title": "Winter Is Coming"}]
            }
        ]
    }
    with mock.patch('resources.lib.kodiUtilities.getString', side_effect=lambda x: "string_%d" % x):
        result = se._SyncEpisodes__getShowAsString(show, short=False)
        assert "Season: 1" in result
        assert "Episodes: 1" in result
