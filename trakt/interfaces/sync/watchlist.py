from trakt.interfaces.base import authenticated
from trakt.interfaces.sync.core.mixins import Get, Add, Remove


class SyncWatchlistInterface(Get, Add, Remove):
    path = 'sync/watchlist'
    flags = {'in_watchlist': True}

    @authenticated
    def get(self, media, store=None):   
        return super(SyncWatchlistInterface, self).get(media, store)
		
    @authenticated
    def add(self, shows=None, movies=None, episodes=None):  
        if not shows and not movies and not episodes:
            raise ValueError('Missing media items')
            
        data = {}
        
        if movies:
            data['movies'] = movies
        elif shows:
            data['shows'] = shows
        elif episodes:
            data['episodes'] = episodes
            
        return super(SyncWatchlistInterface, self).add(data)
        
        
    @authenticated
    def remove(self, shows=None, movies=None, episodes=None):
        if not shows and not movies and not episodes:
            raise ValueError('Missing media items to remove')
            
        data = {}
        
        if movies:
            data['movies'] = movies
        elif shows:
            data['shows'] = shows
        elif episodes:
            data['episodes'] = episodes
            
        return super(SyncHistoryInterface, self).remove(data)

    #
    #    Shortcut methods
    #
    
    @authenticated
    def shows(self, store=None):
        return self.get('shows', store)

    @authenticated
    def seasons(self, store=None):
        return self.get('seasons', store)

    @authenticated
    def episodes(self, store=None):
        return self.get('episodes', store)

    @authenticated
    def movies(self, store=None):
        return self.get('movies', store)
    