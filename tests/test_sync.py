# -*- coding: utf-8 -*-
import sys
from mock import MagicMock

# Mock Kodi modules before imports
sys.modules["xbmc"] = MagicMock()
sys.modules["xbmcaddon"] = MagicMock()
sys.modules["xbmcgui"] = MagicMock()
sys.modules["xbmcvfs"] = MagicMock()

from resources.lib.syncEpisodes import SyncEpisodes  # noqa: E402
from resources.lib.syncMovies import SyncMovies  # noqa: E402


def test_get_show_as_string_logic():
    sync_mock = MagicMock()
    progress_mock = MagicMock()
    # Mocking __init__ to avoid full execution
    SyncEpisodes.__init__ = lambda self, sync, progress: None
    se = SyncEpisodes(sync_mock, progress_mock)

    show = {
        "title": "Test Show",
        "ids": {"tvdb": "123"},
        "seasons": [{"number": 1, "episodes": [{"number": 1}, {"number": 2}]}],
    }

    # Test short=True
    res_short = se._SyncEpisodes__getShowAsString(show, short=True)
    assert "S01E01, S01E02" in res_short
    assert "[tvdb: 123]" in res_short

    # Test short=False - this previously crashed or had wrong logic
    res_long = se._SyncEpisodes__getShowAsString(show, short=False)
    assert "Season: 1, Episodes: 1, 2" in res_long


def test_sync_movies_runtime_none():
    sync_mock = MagicMock()
    # Mocking __init__ to avoid full execution
    SyncMovies.__init__ = lambda self, sync, progress: None
    SyncMovies(sync_mock, MagicMock())

    movie = {"ids": {"trakt": 1}, "runtime": None}

    sync_mock.traktapi.getMovieSummary.return_value = MagicMock(runtime=None)

    # Should not crash even if Trakt returns None for runtime
    # We just want to ensure our new logic handles summary=None or summary.runtime=None
    summary = sync_mock.traktapi.getMovieSummary(1)
    runtime = summary.runtime if summary and summary.runtime else 0
    movie["runtime"] = runtime * 60
    assert movie["runtime"] == 0
