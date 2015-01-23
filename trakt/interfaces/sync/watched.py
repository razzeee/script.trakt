from trakt.interfaces.sync.core.mixins import Get


class SyncWatchedInterface(Get):
    path = 'sync/watched'
    flags = {'is_watched': True}

    @authenticated
    def get(self, media, store=None):   
        return super(SyncWatchedInterface, self).get(media, store)

    #
    #    Shortcut methods
    #
    
    @authenticated
    def shows(self, store=None):
        return self.get('shows', store)

    @authenticated
    def movies(self, store=None):
        return self.get('movies', store)