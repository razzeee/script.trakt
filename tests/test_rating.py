# -*- coding: utf-8 -*-
import mock
import sys
import pytest

# Mock Kodi modules before importing project modules
xbmc_mock = mock.Mock()
sys.modules["xbmc"] = xbmc_mock
sys.modules["xbmcgui"] = mock.Mock()
sys.modules["xbmcaddon"] = mock.Mock()

from resources.lib import rating  # noqa: E402

def test_rateMedia_handles_none_items():
    # Verify that None items in itemsToRate are skipped without raising TypeError
    itemsToRate = [None, {"title": "Test", "user": {"ratings": {"rating": 5}}}]

    with mock.patch('resources.lib.utilities.isValidMediaType', return_value=True), \
         mock.patch('resources.lib.utilities.getFormattedItemName', return_value="Test"), \
         mock.patch('resources.lib.kodiUtilities.getSettingAsBool', return_value=True), \
         mock.patch('resources.lib.rating.RatingDialog') as mock_dialog:
        # This should not raise TypeError
        rating.rateMedia("movie", itemsToRate)
        assert mock_dialog.called
