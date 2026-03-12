# -*- coding: utf-8 -*-
import mock
import sys
import pytest

# Mock Kodi modules before importing project modules
xbmc_mock = mock.Mock()
sys.modules["xbmc"] = xbmc_mock
sys.modules["xbmcgui"] = mock.Mock()
sys.modules["xbmcaddon"] = mock.Mock()

from resources.lib import scrobbler  # noqa: E402

def test_playbackEnded_skips_none_curVideoInfo():
    api_mock = mock.Mock()
    s = scrobbler.Scrobbler(api_mock)
    s.curVideoInfo = None
    s.curVideo = {"type": "movie"}
    s.isPlaying = True
    s.watchedTime = 100
    s.videoDuration = 1000

    xbmc_mock.Player().isPlayingVideo.return_value = False
    xbmc_mock.PlayList.return_value.getposition.return_value = 0
    xbmc_mock.getCondVisibility.return_value = False

    with mock.patch('resources.lib.scrobbler.ratingCheck') as mock_ratingCheck:
        s.playbackEnded()
        # Verify that ratingCheck is not called because curVideoInfo was None and not appended
        assert not mock_ratingCheck.called

def test_scrobble_handles_zero_duration():
    api_mock = mock.Mock()
    s = scrobbler.Scrobbler(api_mock)
    s.curVideo = {"type": "episode", "multi_episode_count": 2}
    s.videoDuration = 0
    s.curVideoInfo = {"title": "Test"}
    s.isMultiPartEpisode = True
    s.watchedTime = 10

    with mock.patch('resources.lib.kodiUtilities.getSettingAsBool', return_value=False):
        # This should not raise ZeroDivisionError
        s._Scrobbler__scrobble("start")
