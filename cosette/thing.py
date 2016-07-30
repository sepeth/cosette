"""Entities in the app."""
# pylint: disable=unsubscriptable-object
import logging
import threading
import weakref
import redis
from cached_property import threaded_cached_property
from cosette import lastfm, youtube, settings


log = logging.getLogger(__name__)
redisconn = redis.StrictRedis(host=settings.REDIS_HOST, db=settings.REDIS_DB)


class Track(object):
    """Represent a single track.

    A track has name, artist and playcount. It has also two more expensive
    property: youtube_id and thumbnail_url.
    Because of some properties are expensive to get, Track objects follow
    flyweight pattern and expensive properties are cached in the corresponding
    track object.
    """
    tracks = weakref.WeakValueDictionary()
    lock = threading.RLock()

    REDIS_KEY_PT = 'track:%s'

    def __new__(cls, artist, name, playcount):
        if isinstance(name, bytes):
            name = name.decode('utf-8')
        key = (artist, name)
        with cls.lock:
            self = cls.tracks.get(key)
            if not self:
                self = object.__new__(cls)
                self.artist = artist
                self.name = name
                self.playcount = int(playcount)
                cls.tracks[key] = self
        return self

    def __repr__(self):
        return "Track(artist=%r, name=%r, playcount=%d)" % (
            self.artist,
            self.name,
            self.playcount,
        )

    def __str__(self):
        return '%s - %s' % (self.artist, self.name)

    def _fill_youtube_values(self, query):
        items = youtube.search(q=query)
        if not items:
            return None
        youtube_id = items[0]['id']['videoId']
        thumbnail = items[0]['snippet']['thumbnails']['default']
        ret = {
            'youtube_id': youtube_id,
            'thumbnail_url': thumbnail['url'],
            'thumbnail_width': thumbnail['width'],
            'thumbnail_height': thumbnail['height']
        }
        rkey = self.REDIS_KEY_PT % query
        redisconn.hmset(rkey, ret)
        return ret

    @threaded_cached_property
    def youtube_id(self):
        """Return youtube id of the track.

        If it is called earlier, return cached value, otherwise check redis first,
        then search youtube if there's nothing in redis.
        """
        query = str(self)
        rkey = self.REDIS_KEY_PT % query
        youtube_id = redisconn.hget(rkey, 'youtube_id')
        if not youtube_id:
            vals = self._fill_youtube_values(query)
            youtube_id = vals['youtube_id']
        if isinstance(youtube_id, bytes):
            youtube_id = youtube_id.decode('utf-8')
        return youtube_id

    @threaded_cached_property
    def thumbnail_url(self):
        """Return url of a thumbnail for the track.

        It works almost the same with youtube_id property.
        """
        query = str(self)
        rkey = self.REDIS_KEY_PT % query
        thumbnail = redisconn.hget(rkey, 'thumbnail_url')
        if not thumbnail:
            vals = self._fill_youtube_values(query)
            thumbnail = vals['thumbnail_url']
        if isinstance(thumbnail, bytes):
            thumbnail = thumbnail.decode('utf-8')
        return thumbnail

    @classmethod
    def save_broken_track(cls, youtube_id, name):
        """Save broken track for later investigation."""
        redisconn.sadd('broken_tracks', '%s|%s' % (youtube_id, name))

    @classmethod
    def save_hits(cls, hits):
        """Save hit tracks to redis.

        Saved tracks are not used at the moment. We are saving them for later use.
        """
        if hits:
            redisconn.sadd('savedhits', *(str(h) for h in hits))


class Artist(object):
    """Represent a single artist.

    Artist objects follow flyweight pattern, this way expensive operations (such as
    calling lastfm or redis) won't happen more than once across requests.
    """
    HIT_THRESHOLD = 0.4
    PLAYCOUNT_THRESHOLD = 10000
    TRACK_COUNT = 3
    SECOND_TRACK_MAX_PLAYCOUNT = 1000000

    artists = weakref.WeakValueDictionary()
    lock = threading.RLock()

    def __new__(cls, name):
        if isinstance(name, bytes):
            name = name.decode('utf-8')
        with cls.lock:
            self = cls.artists.get(name)
            if not self:
                self = object.__new__(cls)
                self.name = name
                cls.artists[name] = self
        return self

    def __repr__(self):
        return "Artist('%s')" % self.name

    def __str__(self):
        return self.name

    @threaded_cached_property
    def similar_artists(self):
        """Return similar artist to the current Artist object.

        This property is cached, if it is not called earlier, it checks redis first,
        then calls lastfm api.
        """
        rkey = 'similar:%s' % self.name
        artists = redisconn.lrange(rkey, 0, -1)
        if not artists:
            if redisconn.sismember('hasnosimilarartist', self.name):
                log.info('%s has no similar artists', self.name)
                return []
            resp = lastfm.call_api(method='artist.getsimilar', artist=self.name)
            artists = [a['name'] for a in resp['similarartists']['artist']]
            if artists:
                redisconn.rpush(rkey, *artists)
                redisconn.sadd('artists', *(a.lower() for a in artists))
            else:
                log.info('No similar artists found for %s', self.name)
                redisconn.sadd('hasnosimilarartist', self.name)
        return [Artist(name) for name in artists]

    @threaded_cached_property
    def top_tracks(self):
        """Return top tracks of the artist.

        Like any expensive property in Cosette, its cost is reduced by using flyweight
        pattern, caching properties, saving the value to the redis for later use. If none
        of the previous steps supplies a value, then calls lastfm api.
        """
        rkey = 'toptracks:%s' % self.name
        toptracks = redisconn.zrevrange(rkey, 0, self.TRACK_COUNT, withscores=True)
        if not toptracks:
            resp = lastfm.call_api(method='artist.gettoptracks', artist=self.name)
            toptracks = {}
            for item in resp['toptracks']['track']:
                toptracks[item['name']] = int(item['playcount'])
            if toptracks:
                redisconn.zadd(rkey, **toptracks)
            # prepare the data as returned from redis
            toptracks = sorted(
                toptracks.items(), key=lambda x: x[1], reverse=True)
            # trim down the track count, we won't need most of it anyway
            toptracks = toptracks[:self.TRACK_COUNT]
        return [Track(artist=self, name=t[0], playcount=t[1])
                for t in toptracks]

    @threaded_cached_property
    def hit_track(self):
        """Return the one hit wonder if there's one, otherwise return None."""
        tracks = self.top_tracks
        try:
            first, second = tracks[0], tracks[1]
        except IndexError:
            return None
        if second.playcount > self.SECOND_TRACK_MAX_PLAYCOUNT:
            return None
        ratio = float(second.playcount) / first.playcount
        if (ratio < self.HIT_THRESHOLD and
                first.playcount > self.PLAYCOUNT_THRESHOLD):
            return first
        return None

    @classmethod
    def is_artist(cls, name):
        """Check the given name is an artist name."""
        return redisconn.sismember('artists', name)


class Tag(object):
    """Represent a tag (or genre).

    Like other things in Cosette, Tag objects follow flyweight pattern as well.
    """
    tags = weakref.WeakValueDictionary()
    lock = threading.RLock()

    def __new__(cls, name):
        with cls.lock:
            self = cls.tags.get(name)
            if not self:
                self = object.__new__(cls)
                self.name = name
                cls.tags[name] = self
            return self

    @threaded_cached_property
    def top_artists(self):
        """Return top artists for the tag."""
        rkey = 'topartists:%s' % self.name
        artists = redisconn.lrange(rkey, 0, -1)
        if not artists:
            if redisconn.sismember('isnottag', self.name):
                log.info('%s has no top artist', self.name)
                return []
            resp = lastfm.call_api(method='tag.gettopartists', tag=self.name, limit=100)
            artists = [t['name'] for t in resp['topartists']['artist']]
            if artists:
                resp = lastfm.call_api(
                    method='tag.gettopartists',
                    tag=self.name,
                    limit=100,
                    page=2
                )
                artists.extend(t['name'] for t in resp['topartists']['artist'])
                redisconn.rpush(rkey, *artists)
                redisconn.sadd('artists', *(a.lower() for a in artists))
            else:
                redisconn.sadd('isnottag', self.name)
                log.info('No top artists has found for %s', self.name)
        return [Artist(name) for name in artists]

    @classmethod
    def is_tag(cls, name):
        """Check the given name is a tag or not."""
        return redisconn.sismember('tags', name)


class Playlist(object):
    """Represent playlist.

    Playlist objects are redis backed.
    """
    def __init__(self, name, length=50):
        self.name = name
        self.length = length

    def add(self, track):
        """Add given track to the playlist."""
        redisconn.lpush(
            self.name,
            '%s|%s|%s' % (track['youtubeId'], track['thumbnailUrl'], track['name'])
        )
        redisconn.ltrim(self.name, 0, self.length - 1)

    def list(self):
        """Fetch playlist from redis and return the tracks as list of dicts."""
        playlist = redisconn.lrange(self.name, 0, -1)
        items = []
        for elem in playlist:
            elem = elem.decode('utf-8')
            youtube_id, thumbnail_url, name = elem.split('|')
            items.append({
                'youtubeId': youtube_id,
                'thumbnailUrl': thumbnail_url,
                'name': name
            })
        return items
