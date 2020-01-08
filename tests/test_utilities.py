# -*- coding: utf-8 -*-
#

import json
import pytest
from resources.lib import utilities


def load_params_from_json(json_path):
    with open(json_path) as f:
        return json.load(f)


def test_isMovie():
    assert utilities.isMovie('movie')


def test_isEpisode():
    assert utilities.isEpisode('episode')


def test_isShow():
    assert utilities.isShow('show')


def test_isSeason():
    assert utilities.isSeason('season')


def test_isValidMediaType_Movie():
    assert utilities.isValidMediaType('movie')


def test_isValidMediaType_Episode():
    assert utilities.isValidMediaType('episode')


def test_isValidMediaType_Show():
    assert utilities.isValidMediaType('show')


def test_isValidMediaType_Season():
    assert utilities.isValidMediaType('season')


def test_chunks():
    movies = load_params_from_json('tests/fixtures/movies.json')
    assert len(utilities.chunks(movies, 1)) == 3


def test_getFormattedItemName_Show():
    data = load_params_from_json('tests/fixtures/show.json')
    assert utilities.getFormattedItemName('show', data) == b'Game of Thrones'


def test_getFormattedItemName_Season():
    data = load_params_from_json('tests/fixtures/season.json')
    assert utilities.getFormattedItemName(
        'season', data) == b'Winter Is Coming - Season 1'


def test_getFormattedItemName_Season2():
    data = load_params_from_json('tests/fixtures/season_no_list.json')
    assert utilities.getFormattedItemName(
        'season', data) == b'Regular Show - Season 8'


def test_getFormattedItemName_Episode():
    data = load_params_from_json('tests/fixtures/episode.json')
    assert utilities.getFormattedItemName(
        'episode', data) == b'S01E01 - Winter Is Coming'


def test_getFormattedItemName_Movie():
    data = load_params_from_json('tests/fixtures/movie.json')
    assert utilities.getFormattedItemName(
        'movie', data) == b'TRON: Legacy (2010)'

# Testing the tilte


def test_regex_tvshow_title_1():
    assert utilities.regex_tvshow('ShowTitle.S01E09')[0] == 'ShowTitle'


def test_regex_tvshow_title_2():
    assert utilities.regex_tvshow('ShowTitle.1x09')[0] == 'ShowTitle'


def test_regex_tvshow_title_3():
    assert utilities.regex_tvshow('ShowTitle.109')[0] == 'ShowTitle'


def test_regex_tvshow_title_4():
    assert utilities.regex_tvshow(
        'ShowTitle.Season 01 - Episode 02')[0] == 'ShowTitle'


def test_regex_tvshow_title_5():
    assert utilities.regex_tvshow('ShowTitle_[s01]_[e01]')[0] == 'ShowTitle'


def test_regex_tvshow_title_6():
    assert utilities.regex_tvshow('ShowTitle - s01ep03')[0] == 'ShowTitle'

# Testing the season


def test_regex_tvshow_season_1():
    assert utilities.regex_tvshow('ShowTitle.S01E09')[1] == 1


def test_regex_tvshow_season_2():
    assert utilities.regex_tvshow('ShowTitle.1x09')[1] == 1


def test_regex_tvshow_season_3():
    assert utilities.regex_tvshow('ShowTitle.109')[1] == 1


def test_regex_tvshow_season_4():
    assert utilities.regex_tvshow('ShowTitle.Season 01 - Episode 02')[1] == 1


def test_regex_tvshow_season_5():
    assert utilities.regex_tvshow('ShowTitle_[s01]_[e01]')[1] == 1


def test_regex_tvshow_season_6():
    assert utilities.regex_tvshow('ShowTitle - s01ep03')[1] == 1

# Testing the episode


def test_regex_tvshow_episode_1():
    assert utilities.regex_tvshow('ShowTitle.S01E09')[2] == 9


def test_regex_tvshow_episode_2():
    assert utilities.regex_tvshow('ShowTitle.1x09')[2] == 9


def test_regex_tvshow_episode_3():
    assert utilities.regex_tvshow('ShowTitle.109')[2] == 9


def test_regex_tvshow_episode_4():
    assert utilities.regex_tvshow('ShowTitle.Season 01 - Episode 09')[2] == 9


def test_regex_tvshow_episode_5():
    assert utilities.regex_tvshow('ShowTitle_[s01]_[e09]')[2] == 9


def test_regex_tvshow_episode_6():
    assert utilities.regex_tvshow('ShowTitle - s01ep09')[2] == 9


def test_regex_year_title_1():
    assert utilities.regex_year('ShowTitle (2014)')[0] == 'ShowTitle'


def test_regex_year_title_2():
    assert utilities.regex_year('ShowTitle')[0] == ''


def test_regex_year_year_1():
    assert utilities.regex_year('ShowTitle (2014)')[1] == '2014'


def test_regex_year_year_2():
    assert utilities.regex_year('ShowTitle')[1] == ''


def test_parseIdToTraktIds_IMDB():
    assert utilities.parseIdToTraktIds('tt1431045', 'movie')[
        0] == {'imdb': 'tt1431045'}


def test_parseIdToTraktIds_TMDB():
    assert utilities.parseIdToTraktIds('20077', 'movie')[
        0] == {'tmdb': '20077'}


def test_parseIdToTraktIds_Tvdb():
    assert utilities.parseIdToTraktIds('4346770', 'show')[
        0] == {'tvdb': '4346770'}


def test_best_id_trakt():
    data = load_params_from_json('tests/fixtures/shows.json')
    assert utilities.best_id(data[1]['show']['ids'], 'show') == 1395


def test_checkExcludePath_Path_Excluded():
    assert utilities.checkExcludePath(
        'C:/excludes/', True, 'C:/excludes/video.mkv', 2)


def test_checkExcludePath_Path_Excluded_Special_Chars():
    assert utilities.checkExcludePath(
        'C:/öäüß%6/', True, 'C:/öäüß%6/video.mkv', 2)


def test_checkExcludePath_Path_NotExcluded():
    assert utilities.checkExcludePath(
        'C:/excludes/', True, 'C:/notexcluded/video.mkv', 2) is False


def test_checkExcludePath_Path_Disabled():
    assert utilities.checkExcludePath(
        'C:/excludes/', False, 'C:/excludes/video.mkv', 2) is False


def test_sanitizeMovies_collected():
    data = load_params_from_json('tests/fixtures/movies_unsanatized.json')
    utilities.sanitizeMovies(data)
    for movie in data:
        result = 'collected' in movie
        if result:
            break

    assert not result


def test_sanitizeMovies_watched():
    data = load_params_from_json('tests/fixtures/movies_unsanatized.json')
    utilities.sanitizeMovies(data)
    for movie in data:
        result = 'watched' in movie
        if result:
            break

    assert not result


def test_sanitizeMovies_movieid():
    data = load_params_from_json('tests/fixtures/movies_unsanatized.json')
    utilities.sanitizeMovies(data)
    for movie in data:
        result = 'movieid' in movie
        if result:
            break

    assert not result


def test_sanitizeMovies_plays():
    data = load_params_from_json('tests/fixtures/movies_unsanatized.json')
    utilities.sanitizeMovies(data)
    for movie in data:
        result = 'plays' in movie
        if result:
            break

    assert not result


def test_sanitizeMovies_userrating():
    data = load_params_from_json('tests/fixtures/movies_unsanatized.json')
    utilities.sanitizeMovies(data)
    for movie in data:
        result = 'userrating' in movie
        if result:
            break

    assert not result


def test_compareMovies_matchByTitleAndYear_collected_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, data2, True) == data3


def test_compareMovies_matchByTitleAndYear_watched_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, data2, True, watched=True) == data3


def test_compareMovies_matchByTitleAndYear_playback_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')

    assert utilities.compareMovies(data1, data2, True, playback=True) == data1


def test_compareMovies_matchByTitleAndYear_rating_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, data2, True, rating=True) == data3


def test_compareMovies_matchByTitleAndYear_collected_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')

    assert utilities.compareMovies(data1, "", True) == data1


def test_compareMovies_matchByTitleAndYear_watched_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, "", True, watched=True) == data3


def test_compareMovies_matchByTitleAndYear_playback_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')

    assert utilities.compareMovies(data1, "", True, playback=True) == data1


def test_compareMovies_matchByTitleAndYear_rating_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')

    assert utilities.compareMovies(data1, "", True, rating=True) == data1

def test_compareMovies_not_matchByTitleAndYear_collected_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, data2, False) == data3


def test_compareMovies_not_matchByTitleAndYear_watched_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, data2, False, watched=True) == data3


def test_compareMovies_not_matchByTitleAndYear_playback_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')

    assert utilities.compareMovies(data1, data2, False, playback=True) == data1


def test_compareMovies_not_matchByTitleAndYear_rating_match():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, data2, False, rating=True) == data3


def test_compareMovies_not_matchByTitleAndYear_collected_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')

    assert utilities.compareMovies(data1, "", False) == data1


def test_compareMovies_not_matchByTitleAndYear_watched_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')
    data3 = load_params_from_json('tests/fixtures/movies_watched.json')

    assert utilities.compareMovies(data1, "", False, watched=True) == data3


def test_compareMovies_not_matchByTitleAndYear_playback_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')

    assert utilities.compareMovies(data1, "", False, playback=True) == data1


def test_compareMovies_not_matchByTitleAndYear_rating_nomatch():
    data1 = load_params_from_json('tests/fixtures/movies_local.json')

    assert utilities.compareMovies(data1, "", False, rating=True) == data1


def test_checkIfNewVersion_unchanged():
    assert utilities.checkIfNewVersion('3.1.3', '3.1.3') == False


def test_checkIfNewVersion_major_new():
    assert utilities.checkIfNewVersion('2.1.3', '3.1.3') == True


def test_checkIfNewVersion_major_old():
    assert utilities.checkIfNewVersion('2.1.3', '1.1.3') == False


def test_checkIfNewVersion_minor_new():
    assert utilities.checkIfNewVersion('2.1.3', '2.4.3') == True


def test_checkIfNewVersion_minor_old():
    assert utilities.checkIfNewVersion('2.6.3', '1.1.3') == False


def test_checkIfNewVersion_revision_new():
    assert utilities.checkIfNewVersion('2.1.510', '3.1.513') == True


def test_checkIfNewVersion_revision_old():
    assert utilities.checkIfNewVersion('2.1.3', '1.1.5') == False


def test_checkIfNewVersion_old_version_empty():
    assert utilities.checkIfNewVersion('', '1.1.5') == True


def test_compareShows_matchByTitleAndYear_no_rating():
    data1 = load_params_from_json('tests/fixtures/compare_shows_local_batman.json')
    data2 = load_params_from_json('tests/fixtures/compare_shows_remote_batman.json')

    assert utilities.compareShows(data1, data2, True, rating=True) == {"shows": []}

def test_compareShows_matchByTitleAndYear_rating_changed():
    data1 = load_params_from_json('tests/fixtures/compare_shows_local_batman_rating.json')
    data2 = load_params_from_json('tests/fixtures/compare_shows_remote_batman.json')
    fixture = load_params_from_json('tests/fixtures/compare_shows_compared_batman.json')

    assert utilities.compareShows(data1, data2, True, rating=True) == fixture


def test_compareShows_not_matchByTitleAndYear_no_rating():
    data1 = load_params_from_json(
        'tests/fixtures/compare_shows_local_batman.json')
    data2 = load_params_from_json(
        'tests/fixtures/compare_shows_remote_batman.json')

    assert utilities.compareShows(data1, data2, False, rating=True) == {"shows": []}


def test_compareShows_not_matchByTitleAndYear_rating_changed():
    data1 = load_params_from_json(
        'tests/fixtures/compare_shows_local_batman_rating.json')
    data2 = load_params_from_json(
        'tests/fixtures/compare_shows_remote_batman.json')
    fixture = load_params_from_json(
        'tests/fixtures/compare_shows_compared_batman.json')

    assert utilities.compareShows(data1, data2, False, rating=True) == fixture


def test_compareEpisodes_matchByTitleAndYear_no_matches():
    data1 = load_params_from_json('tests/fixtures/compare_shows_local_batman.json')
    data2 = load_params_from_json('tests/fixtures/compare_shows_remote_batman.json')

    assert utilities.compareEpisodes(data1, data2, True) == {"shows": []}


def test_compareEpisodes_matchByTitleAndYear_local_episode_added():
    data1 = load_params_from_json('tests/fixtures/compare_shows_local_batman.json')
    data2 = load_params_from_json('tests/fixtures/compare_shows_remote_batman_episode.json')
    fixture = load_params_from_json('tests/fixtures/compare_shows_batman_episode_to_add.json')

    assert utilities.compareEpisodes(data1, data2, True) == fixture


def test_compareEpisodes_not_matchByTitleAndYear_no_matches():
    data1 = load_params_from_json(
        'tests/fixtures/compare_shows_local_batman.json')
    data2 = load_params_from_json(
        'tests/fixtures/compare_shows_remote_batman.json')

    assert utilities.compareEpisodes(data1, data2, False) == {"shows": []}


def test_compareEpisodes_not_matchByTitleAndYear_local_episode_added():
    data1 = load_params_from_json(
        'tests/fixtures/compare_shows_local_batman.json')
    data2 = load_params_from_json(
        'tests/fixtures/compare_shows_remote_batman_episode.json')
    fixture = load_params_from_json(
        'tests/fixtures/compare_shows_batman_episode_to_add.json')

    assert utilities.compareEpisodes(data1, data2, False) == fixture

def test_findMediaObject_not_matchByTitleAndYear_should_not_match():
    data1 = load_params_from_json('tests/fixtures/movies_local_blind.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote_blind_no_match.json')

    assert utilities.findMediaObject(data1, data2, False) == None


def test_findMediaObject_not_matchByTitleAndYear_should_match():
    data1 = load_params_from_json('tests/fixtures/movies_local_blind.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote_blind_match.json')

    assert utilities.findMediaObject(data1, data2, False) == data1


def test_findMediaObject_not_matchByTitleAndYear_add_collection():
    data1 = load_params_from_json('tests/fixtures/movies_local_chaos.json')
    data2 = []

    assert utilities.findMediaObject(data1, data2, False) == None


def test_findMediaObject_not_matchByTitleAndYear_add_collection_same_year_title_movie_in_collection():
    data1 = load_params_from_json('tests/fixtures/movies_local_chaos.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote_chaos_match.json')

    assert utilities.findMediaObject(data1, data2, False) == None


def test_findMediaObject_match_by_title_should_match():
    data1 = load_params_from_json('tests/fixtures/movies_local_blind.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote_blind_no_match.json')

    assert utilities.findMediaObject(data1, data2, True) == data2[0]


def test_findMediaObject_matchByTitleAndYear_should_match():
    data1 = load_params_from_json('tests/fixtures/movies_local_blind.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote_blind_match.json')

    assert utilities.findMediaObject(data1, data2, True) == data1


def test_findMediaObject_matchByTitleAndYear_add_collection():
    data1 = load_params_from_json('tests/fixtures/movies_local_chaos.json')
    data2 = []

    assert utilities.findMediaObject(data1, data2, True) == None


def test_findMediaObject_matchByTitleAndYear_add_collection_same_year_title_movie_in_collection():
    data1 = load_params_from_json('tests/fixtures/movies_local_chaos.json')
    data2 = load_params_from_json('tests/fixtures/movies_remote_chaos_match.json')

    assert utilities.findMediaObject(data1, data2, True) == data2[0]


def test_countEpisodes1():
    data1 = load_params_from_json('tests/fixtures/compare_shows_local_batman.json')

    assert utilities.countEpisodes(data1) == 6


def test_countEpisodes2():
    data1 = load_params_from_json('tests/fixtures/compare_shows_remote_batman_episode.json')

    assert utilities.countEpisodes(data1) == 5
