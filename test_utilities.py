import unittest
from utilities import isMovie, isEpisode, isShow, isSeason

class TestUtilities(unittest.TestCase):
 
    def setUp(self):
        pass
 
    def test_isMovie(self):
        self.assertEqual( utilities.isMovie('movie'), 'movie')
 
    def test_isEpisode(self):
        self.assertEqual( utilities.isEpisode('episode'), 'episode')

    def test_isShow(self):
        self.assertEqual( utilities.isShow('show'), 'show')
 
    def test_isSeason(self):
        self.assertEqual( utilities.isSeason('season'), 'season')
