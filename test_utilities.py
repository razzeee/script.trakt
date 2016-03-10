import unittest
import utilities

class TestUtilities(unittest.TestCase):

    def setUp(self):
        pass

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