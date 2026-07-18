# -*- coding: utf-8 -*-

import sys
import urllib.error

import mock


class WindowXMLDialog(object):
    pass


xbmc_mock = mock.Mock()
sys.modules["xbmc"] = xbmc_mock
xbmcgui_mock = mock.Mock()
xbmcgui_mock.WindowXMLDialog = WindowXMLDialog
sys.modules["xbmcgui"] = xbmcgui_mock
xbmcaddon_mock = mock.Mock()
xbmcaddon_mock.Addon.return_value.getAddonInfo.return_value = "3.8.2"
sys.modules["xbmcaddon"] = xbmcaddon_mock

from resources.lib import utilities  # noqa: E402
from resources.lib.traktapi import TraktClient, TraktObject, TraktSeason, traktAPI  # noqa: E402


def test_trakt_object_exposes_legacy_contract():
    item = TraktObject(
        {
            "title": "Example Show",
            "ids": {"trakt": 1, "tvdb": 2},
            "seasons": [
                {
                    "number": 1,
                    "episodes": [{"number": 2, "title": "Episode"}],
                }
            ],
        }
    )

    assert item.title == "Example Show"
    assert dict(item.keys) == {"trakt": 1, "tvdb": 2}
    assert item.to_dict()["title"] == "Example Show"
    assert item.episodes[2].title == "Episode"
    assert item.episodes[2].season == 1


def test_merge_movie_sync_payloads_preserves_object_shape():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_object(
        store,
        {
            "collected_at": "2024-01-01",
            "movie": {"title": "Movie", "ids": {"trakt": 1}},
        },
        "movie",
        ("collected_at",),
    )
    api._merge_object(
        store,
        {"plays": 2, "movie": {"title": "Movie", "ids": {"trakt": 1}}},
        "movie",
        ("plays",),
    )

    movie = store[1]
    assert movie.to_dict()["collected_at"] == "2024-01-01"
    assert movie.to_dict()["plays"] == 2


def test_merge_movie_collection_payload_preserves_legacy_defaults():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_object(
        store,
        {
            "collected_at": "2024-01-01",
            "movie": {"title": "Movie", "year": 2024, "ids": {"trakt": 1}},
        },
        "movie",
        ("collected_at",),
    )

    movie = store[1].to_dict()
    assert movie["collected"] == 1
    assert movie["watched"] == 0
    assert movie["plays"] == 0
    assert movie["in_watchlist"] == 0
    assert movie["progress"] is None
    assert movie["last_watched_at"] is None
    assert movie["paused_at"] is None


def test_merge_movie_watched_payload_preserves_legacy_defaults():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_object(
        store,
        {"plays": 2, "movie": {"title": "Movie", "ids": {"trakt": 1}}},
        "movie",
        ("plays",),
    )

    movie = store[1].to_dict()
    assert movie["watched"] == 1
    assert movie["collected"] == 0
    assert movie["plays"] == 2
    assert movie["in_watchlist"] == 0
    assert movie["progress"] is None
    assert movie["collected_at"] is None
    assert movie["paused_at"] is None


def test_collected_only_trakt_movie_does_not_break_watched_compare():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_object(
        store,
        {
            "collected_at": "2024-01-01",
            "movie": {"title": "Movie", "year": 2024, "ids": {"trakt": 1}},
        },
        "movie",
        ("collected_at",),
    )

    kodi_movies = [
        {
            "title": "Movie",
            "year": 2024,
            "ids": {"trakt": 1},
            "watched": 1,
            "plays": 1,
            "movieid": 10,
        }
    ]
    trakt_movies = [movie.to_dict() for movie in store.values()]

    assert (
        utilities.compareMovies(kodi_movies, trakt_movies, True, watched=True)
        == kodi_movies
    )


def test_merge_show_payloads_merges_nested_episodes():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_show(
        store,
        {
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "seasons": [
                {"number": 1, "episodes": [{"number": 2, "collected_at": "now"}]}
            ],
        },
        (),
    )
    api._merge_show(
        store,
        {
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "seasons": [{"number": 1, "episodes": [{"number": 2, "plays": 3}]}],
        },
        (),
    )

    episode = store[1].to_dict()["seasons"][0]["episodes"][0]
    assert episode["collected_at"] == "now"
    assert episode["plays"] == 3


def test_merge_show_collection_payload_preserves_legacy_episode_defaults():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_show(
        store,
        {
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "seasons": [
                {
                    "number": 1,
                    "episodes": [{"number": 2, "collected_at": "now"}],
                }
            ],
        },
        ("collected_at",),
    )

    episode = store[1].to_dict()["seasons"][0]["episodes"][0]
    assert episode["collected"] == 1
    assert episode["watched"] == 0
    assert episode["plays"] == 0
    assert episode["in_watchlist"] == 0
    assert episode["progress"] is None
    assert episode["last_watched_at"] is None
    assert episode["paused_at"] is None


def test_merge_show_watched_payload_preserves_legacy_episode_defaults():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_show(
        store,
        {
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "seasons": [{"number": 1, "episodes": [{"number": 2, "plays": 3}]}],
        },
        ("plays",),
    )

    episode = store[1].to_dict()["seasons"][0]["episodes"][0]
    assert episode["watched"] == 1
    assert episode["collected"] == 0
    assert episode["plays"] == 3
    assert episode["in_watchlist"] == 0
    assert episode["progress"] is None
    assert episode["collected_at"] is None
    assert episode["paused_at"] is None


def test_merge_show_preserves_episode_flags_across_collection_and_watched_payloads():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_show(
        store,
        {
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "seasons": [
                {
                    "number": 1,
                    "episodes": [{"number": 2, "collected_at": "now"}],
                }
            ],
        },
        ("collected_at",),
    )
    api._merge_show(
        store,
        {
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "seasons": [{"number": 1, "episodes": [{"number": 2, "plays": 3}]}],
        },
        ("plays",),
    )

    episode = store[1].to_dict()["seasons"][0]["episodes"][0]
    assert episode["collected"] == 1
    assert episode["watched"] == 1
    assert episode["plays"] == 3


def test_merge_episode_rating_payload_attaches_rating_to_episode():
    api = traktAPI.__new__(traktAPI)
    store = {}

    api._merge_show(
        store,
        {
            "rated_at": "2024-01-01",
            "rating": 8,
            "show": {"title": "Show", "ids": {"trakt": 1}},
            "episode": {"season": 1, "number": 2, "title": "Episode"},
        },
        ("rated_at", "rating"),
    )

    show = store[1].to_dict()
    episode = show["seasons"][0]["episodes"][0]
    assert "rating" not in show
    assert episode["rating"] == 8
    assert episode["rated_at"] == "2024-01-01"


def test_show_summary_defaults_seasons_for_rating_compatibility():
    api = traktAPI.__new__(traktAPI)
    api._get = mock.Mock(return_value={"title": "Show", "ids": {"trakt": 1}})

    show = api.getShowSummary("1").to_dict()

    assert show["seasons"] == []


def test_wrap_search_episode_result_exposes_show_and_pk():
    api = traktAPI.__new__(traktAPI)

    result = api._wrap_search_results(
        [
            {
                "show": {"title": "Show", "ids": {"trakt": 1}},
                "episode": {"season": 4, "number": 5, "title": "Episode"},
            }
        ]
    )

    assert result[0].show.title == "Show"
    assert result[0].pk == (4, 5)
    assert result[0].title == "Episode"


def test_text_query_skips_episode_search_not_in_current_contract():
    api = traktAPI.__new__(traktAPI)
    api.client = TraktClient("id", "secret", "ua")
    api._get_all_pages = mock.Mock(return_value=[])

    assert api.getTextQuery("Episode", "episode", None) is None
    api._get_all_pages.assert_not_called()


def test_text_query_skips_unknown_search_type_not_in_openapi_enum():
    api = traktAPI.__new__(traktAPI)
    api.client = TraktClient("id", "secret", "ua")
    api._get_all_pages = mock.Mock(return_value=[])

    assert api.getTextQuery("List", "list", None) is None
    api._get_all_pages.assert_not_called()


def test_show_season_episode_keys_preserve_legacy_season_episode_pair():
    season = TraktSeason({"number": 3, "episodes": [{"number": 7, "title": "Episode"}]})

    assert season.episodes[7].keys[0] == (3, 7)


def test_client_build_path_omits_empty_params():
    client = TraktClient("id", "secret", "ua")

    assert (
        client.build_path("/search/show", {"query": "Batman", "years": None})
        == "/search/show?query=Batman"
    )


def test_client_build_path_appends_to_existing_query():
    client = TraktClient("id", "secret", "ua")

    assert (
        client.build_path("/search/show?query=Batman", {"page": 2, "limit": 100})
        == "/search/show?query=Batman&page=2&limit=100"
    )


def test_get_all_pages_follows_pagination_headers():
    api = traktAPI.__new__(traktAPI)
    api.client = TraktClient("id", "secret", "ua")
    api._get = mock.Mock(
        side_effect=[
            ([{"title": "One"}], {"X-Pagination-Page-Count": "2"}),
            ([{"title": "Two"}], {"X-Pagination-Page-Count": "2"}),
        ]
    )

    result = api._get_all_pages("/sync/collection/movies", authorized=True)

    assert result == [{"title": "One"}, {"title": "Two"}]
    api._get.assert_has_calls(
        [
            mock.call(
                "/sync/collection/movies?page=1&limit=100",
                authorized=True,
                timeout=90,
                include_headers=True,
            ),
            mock.call(
                "/sync/collection/movies?page=2&limit=100",
                authorized=True,
                timeout=90,
                include_headers=True,
            ),
        ]
    )


def test_get_all_pages_merges_extra_params_into_query():
    api = traktAPI.__new__(traktAPI)
    api.client = TraktClient("id", "secret", "ua")
    api._get = mock.Mock(return_value=([{"title": "One"}], {}))

    api._get_all_pages(
        "/sync/watched/shows", authorized=True, params={"extended": "progress"}
    )

    api._get.assert_called_once_with(
        "/sync/watched/shows?page=1&limit=100&extended=progress",
        authorized=True,
        timeout=90,
        include_headers=True,
    )


def test_get_all_ratings_fetches_current_rating_bucket_endpoints():
    api = traktAPI.__new__(traktAPI)
    api._get_all_pages = mock.Mock(return_value=[])

    api._get_all_ratings("movies")

    assert api._get_all_pages.call_args_list[0] == mock.call(
        "/sync/ratings/movies/1", authorized=True, timeout=90
    )
    assert api._get_all_pages.call_args_list[-1] == mock.call(
        "/sync/ratings/movies/10", authorized=True, timeout=90
    )
    assert api._get_all_pages.call_count == 10


def test_movie_playback_progress_uses_pagination():
    api = traktAPI.__new__(traktAPI)
    api._get_all_pages = mock.Mock(
        return_value=[
            {"progress": 50, "movie": {"title": "Movie", "ids": {"trakt": 1}}}
        ]
    )

    result = api.getMoviePlaybackProgress()

    api._get_all_pages.assert_called_once_with(
        "/sync/playback/movies", authorized=True, timeout=90
    )
    assert result[0].to_dict()["progress"] == 50


def test_episode_playback_progress_uses_pagination():
    api = traktAPI.__new__(traktAPI)
    api._get_all_pages = mock.Mock(
        return_value=[
            {
                "progress": 50,
                "show": {"title": "Show", "ids": {"trakt": 1}},
                "episode": {"season": 1, "number": 2, "title": "Episode"},
            }
        ]
    )

    result = api.getEpisodePlaybackProgress()

    api._get_all_pages.assert_called_once_with(
        "/sync/playback/episodes", authorized=True, timeout=90
    )
    episode = result[0].to_dict()["seasons"][0]["episodes"][0]
    assert episode["progress"] == 50


def test_get_shows_watched_requests_progress_and_paginates():
    api = traktAPI.__new__(traktAPI)
    api._get_all_pages = mock.Mock(
        return_value=[
            {
                "plays": 3,
                "last_watched_at": "2026-01-01T00:00:00.000Z",
                "show": {"title": "Show", "ids": {"trakt": 1}},
                "seasons": [{"number": 1, "episodes": [{"number": 1, "plays": 1}]}],
            }
        ]
    )

    result = api.getShowsWatched({})

    # extended=progress is what restores the season/episode breakdown (Trakt 2026
    # API change); without it episode watched-state can't be synced.
    api._get_all_pages.assert_called_once_with(
        "/sync/watched/shows",
        authorized=True,
        timeout=90,
        params={"extended": "progress"},
    )
    episode = result[1].to_dict()["seasons"][0]["episodes"][0]
    assert episode["plays"] == 1


def test_get_shows_collected_paginates():
    api = traktAPI.__new__(traktAPI)
    api._get_all_pages = mock.Mock(return_value=[])

    api.getShowsCollected({})

    api._get_all_pages.assert_called_once_with(
        "/sync/collection/shows", authorized=True, timeout=90
    )


def test_get_movies_watched_paginates():
    api = traktAPI.__new__(traktAPI)
    api._get_all_pages = mock.Mock(return_value=[])

    api.getMoviesWatched({})

    api._get_all_pages.assert_called_once_with(
        "/sync/watched/movies", authorized=True, timeout=90
    )


def test_client_retries_once_after_rate_limit_retry_after():
    client = TraktClient("id", "secret", "ua")
    rate_limit = urllib.error.HTTPError(
        "https://api.trakt.tv/search/movie",
        429,
        "Too Many Requests",
        {"Retry-After": "1"},
        None,
    )
    response = mock.Mock()
    response.__enter__ = mock.Mock(return_value=response)
    response.__exit__ = mock.Mock(return_value=None)
    response.read.return_value = b'{"ok": true}'
    opener = mock.Mock()
    opener.open = mock.Mock(side_effect=[rate_limit, response])

    with mock.patch(
        "resources.lib.traktapi.urllib.request.build_opener", return_value=opener
    ):
        with mock.patch("resources.lib.traktapi.time.sleep") as sleep:
            result = client.request("GET", "/search/movie")

    assert result == {"ok": True}
    sleep.assert_called_once_with(1)
    assert opener.open.call_count == 2


def test_add_to_history_disables_automatic_retry():
    api = traktAPI.__new__(traktAPI)
    api._request = mock.Mock(return_value={})

    api.addToHistory({"movies": []})

    api._request.assert_called_once_with(
        "POST",
        "/sync/history",
        body={"movies": []},
        authorized=True,
        timeout=30,
        retry=False,
    )


def test_request_refreshes_token_but_does_not_replay_when_retry_disabled():
    api = traktAPI.__new__(traktAPI)
    api.authorization = {"access_token": "expired", "refresh_token": "refresh"}
    api.client = mock.Mock()
    api.client.client_id = "id"
    api.client.client_secret = "secret"
    unauthorized = urllib.error.HTTPError(
        "https://api.trakt.tv/sync/history", 401, "Unauthorized", {}, None
    )
    api.client.request = mock.Mock(
        side_effect=[unauthorized, {"access_token": "new", "refresh_token": "next"}]
    )
    api.on_token_refreshed = mock.Mock()

    result = api._request(
        "POST",
        "/sync/history",
        body={"movies": []},
        authorized=True,
        retry=False,
    )

    assert result is None
    api.on_token_refreshed.assert_called_once_with(
        {"access_token": "new", "refresh_token": "next"}
    )
    assert api.client.request.call_count == 2


def test_client_returns_none_on_transport_error():
    client = TraktClient("id", "secret", "ua")
    opener = mock.Mock()
    opener.open = mock.Mock(side_effect=urllib.error.URLError("offline"))

    with mock.patch(
        "resources.lib.traktapi.urllib.request.build_opener", return_value=opener
    ):
        result = client.request("GET", "/users/settings")

    assert result is None


def test_device_poll_continues_on_pending_then_authenticates():
    api = traktAPI.__new__(traktAPI)
    api.client = mock.Mock()
    api.client.client_id = "id"
    api.client.client_secret = "secret"
    api.client.request = mock.Mock(
        side_effect=[
            (None, 400),
            ({"access_token": "token", "refresh_token": "refresh"}, None),
        ]
    )
    api.on_authenticated = mock.Mock()
    api.on_expired = mock.Mock()

    with mock.patch("resources.lib.traktapi.time.sleep"):
        api._poll_device_token(
            {"device_code": "device", "expires_in": 30, "interval": 5}
        )

    api.on_authenticated.assert_called_once_with(
        {"access_token": "token", "refresh_token": "refresh"}
    )
    api.on_expired.assert_not_called()


def test_device_poll_stops_on_denied_status():
    api = traktAPI.__new__(traktAPI)
    api.client = mock.Mock()
    api.client.client_id = "id"
    api.client.client_secret = "secret"
    api.client.request = mock.Mock(return_value=(None, 418))
    api.on_authenticated = mock.Mock()
    api.on_expired = mock.Mock()

    api._poll_device_token({"device_code": "device", "expires_in": 30, "interval": 5})

    api.on_authenticated.assert_not_called()
    api.on_expired.assert_called_once_with()


def test_device_poll_slows_down_on_rate_limit_status():
    api = traktAPI.__new__(traktAPI)
    api.client = mock.Mock()
    api.client.client_id = "id"
    api.client.client_secret = "secret"
    api.client.request = mock.Mock(
        side_effect=[
            (None, 429),
            ({"access_token": "token", "refresh_token": "refresh"}, None),
        ]
    )
    api.on_authenticated = mock.Mock()
    api.on_expired = mock.Mock()

    with mock.patch("resources.lib.traktapi.time.sleep") as sleep:
        api._poll_device_token(
            {"device_code": "device", "expires_in": 30, "interval": 5}
        )

    sleep.assert_called_once_with(6)
    api.on_authenticated.assert_called_once_with(
        {"access_token": "token", "refresh_token": "refresh"}
    )
