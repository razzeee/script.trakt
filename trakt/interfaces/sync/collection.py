from trakt.interfaces.sync.core.mixins import Get, Add, Remove


class SyncCollectionInterface(Get, Add, Remove):
    path = 'sync/collection'
    flags = {'is_collected': True}
    
    @authenticated
    def get(self, media, store=None):   
        return super(SyncCollectionInterface, self).get(media, store)
            
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
            
        return super(SyncCollectionInterface, self).add(data)
        
        
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
            
        return super(SyncCollectionInterface, self).remove(data)
        
        
    #
    #    Shortcut methods
    #
    
    @authenticated
    def getShows(self, store=None):
        return self.get('shows', store)

    @authenticated
    def getMovies(self, store=None):
        return self.get('movies', store)
