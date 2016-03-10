import unittest
import utilities

class TestUtilities(unittest.TestCase):
 
    def setUp(self):
        pass
 
    def test_isMovie(self):
        self.assertEqual( utilities.isMovie('movie'), 'movie')
 
    def test_isEpisode(self):
        self.assertEqual( utilities.isMovie('episode'), 'episode')

    def test_isShow(self):
        self.assertEqual( utilities.isMovie('show'), 'show')
 
    def test_isSeasone(self):
        self.assertEqual( utilities.isMovie('season'), 'season')
