# -*- coding: utf-8 -*-

import os
import sqlite3
from json import loads, dumps

from time import sleep

try:
    from _thread import get_ident
except ImportError:
    from _dummy_thread import get_ident

import xbmcvfs
import xbmcaddon
import logging
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

__addon__ = xbmcaddon.Addon('script.trakt')

# code from http://flask.pocoo.org/snippets/88/ with some modifications
class SqliteQueue(object):

    _create = (
                'CREATE TABLE IF NOT EXISTS queue '
                '('
                '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
                '  item BLOB'
                ')'
                )
    _count = 'SELECT COUNT(*) FROM queue'
    _iterate = 'SELECT id, item FROM queue'
    _append = 'INSERT INTO queue (item) VALUES (?)'
    _write_lock = 'BEGIN IMMEDIATE'
    _get = (
            'SELECT id, item FROM queue '
            'ORDER BY id LIMIT 1'
            )
    _del = 'DELETE FROM queue WHERE id = ?'
    _peek = (
            'SELECT item FROM queue '
            'ORDER BY id LIMIT 1'
            )
    _purge = 'DELETE FROM queue'

    def __init__(self):
        self.path = xbmcvfs.translatePath(__addon__.getAddonInfo("profile"))
        if not xbmcvfs.exists(self.path):
            logger.debug("Making path structure: %s" % repr(self.path))
            xbmcvfs.mkdir(self.path)
        self.path = os.path.join(self.path, 'queue.db')
        self._connection_cache = {}
        with self._get_conn() as conn:
            conn.execute(self._create)

    def __len__(self) -> int:
        with self._get_conn() as conn:
            executed = conn.execute(self._count).fetchone()[0]
        return executed

    def __iter__(self) -> Iterator[Any]:
        with self._get_conn() as conn:
            for _, obj_buffer in conn.execute(self._iterate):
                yield loads(obj_buffer)

    def _get_conn(self) -> sqlite3.Connection:
        id = get_ident()
        if id not in self._connection_cache:
            self._connection_cache[id] = sqlite3.Connection(self.path, timeout=60)
        return self._connection_cache[id]

    def purge(self) -> None:
        with self._get_conn() as conn:
            conn.execute(self._purge)

    def append(self, obj: Any) -> None:
        obj_buffer = dumps(obj)
        with self._get_conn() as conn:
            conn.execute(self._append, (obj_buffer,))

    def get(self, sleep_wait: bool = True) -> Optional[Any]:
        keep_pooling = True
        wait = 0.1
        max_wait = 2
        tries = 0
        with self._get_conn() as conn:
            id = None
            while keep_pooling:
                conn.execute(self._write_lock)
                cursor = conn.execute(self._get)
                row = cursor.fetchone()
                if row:
                    id, obj_buffer = row
                    keep_pooling = False
                else:
                    conn.commit()  # unlock the database
                    if not sleep_wait:
                        keep_pooling = False
                        continue
                    tries += 1
                    sleep(wait)
                    wait = min(max_wait, tries / 10 + wait)
            if id:
                conn.execute(self._del, (id,))
                return loads(obj_buffer)
        return None

    def peek(self) -> Optional[Any]:
        with self._get_conn() as conn:
            cursor = conn.execute(self._peek)
            row = cursor.fetchone()
            if row:
                return loads(row[0])
            return None
