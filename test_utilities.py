import pytest
import utilities

class TestUtilities:

    def test_isMovie(self):
        assert utilities.isMovie('movie')

    def test_isEpisode(self):
        assert utilities.isEpisode('episode')

    def test_isShow(self):
        assert utilities.isShow('show')

    def test_isSeason(self):
        assert utilities.isSeason('season')

    def test_parseIdToTraktIds_IMDB(self):
        assert utilities.parseIdToTraktIds('tt1431045', 'movie')[0] == {'imdb': 'tt1431045'}

    def test_parseIdToTraktIds_TMDB(self):
        assert utilities.parseIdToTraktIds('20077', 'movie')[0] == {'tmdb': '20077'}

    def test_parseIdToTraktIds_Tvdb(self):
        assert utilities.parseIdToTraktIds('4346770', 'show')[0] == {'tvdb': '4346770'}
