from trakt.interfaces.sync.core.mixins import Add, Remove


class SyncHistoryInterface(Add, Remove):
    path = 'sync/history'
    
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
            
        return super(SyncHistoryInterface, self).add(data)
        
        
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