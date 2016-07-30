"""App Entry Point, initializes wsgi app, sets the routes."""
import json
import logging
import random

from gevent import queue, pool
from flask import Flask, render_template, request, Response

from cosette.thing import Playlist, Artist, Tag, Track

log = logging.getLogger(__name__)
app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True


@app.route('/')
def index():
    """Main page."""
    playlist = Playlist('global_playlist').list()
    if playlist:
        down_under, playlist = playlist[0], playlist[1:]
        random.shuffle(playlist)
        playlist = [down_under] + playlist
    return render_template(
        'index.html',
        global_playlist=playlist,
        first_song=playlist[0]['youtubeId'] if playlist else None,
    )


@app.route('/tracks')
def tracks():
    """Event Source endpoint for search queries."""
    query = request.args.get('q') or 'pink floyd'
    query = query.lower()

    artists = set()
    if Tag.is_tag(query):
        log.info('Query "%s" seems a tag', query)
        artists.update(Tag(name=query).top_artists)
    elif Artist.is_artist(query):
        log.info('Query "%s" seems an artist name', query)
        artists.update(Artist(name=query).similar_artists)
    else:
        log.info('Query "%s" might be tag or artist', query)
        artists.update(Artist(name=query).similar_artists)
        artists.update(Tag(name=query).top_artists)

    def fetch_artist(artist):
        """Fetch helper to run inside greenlet."""
        hit = artist.hit_track
        if hit:
            if not hit.youtube_id:
                log.info("Couldn't find youtube id, skipping track %s", hit)
                return
            hit_queue.put({
                'name': str(hit),
                'youtubeId': hit.youtube_id,
                'thumbnailUrl': hit.thumbnail_url,
            })

    hit_queue = queue.Queue()
    fetch_pool = pool.Pool(10)
    glet = fetch_pool.map_async(fetch_artist, artists)

    def gen():
        """Generate response by yielding to event source."""
        hits = []
        tried = 0
        while glet:
            try:
                hit = hit_queue.get(timeout=1)
            except queue.Empty:
                tried += 1
                if tried >= 30:
                    log.info('Query "%s" took too much, giving up', query)
                    fetch_pool.kill()
                    break
                if glet:
                    continue
                else:
                    break
            hits.append(hit)
            yield ('event: song\ndata: %s\n\n' % json.dumps(hit)).encode('utf-8')
        Track.save_hits(hits)
        yield 'event: finish\ndata: finish\n\n'.encode('utf-8')

    return Response(gen(), mimetype='text/event-stream')


@app.route('/broken-track', methods=['POST'])
def broken_track():
    """Mark a track as broken for later investigation."""
    youtube_id = request.form['youtube_id']
    name = request.form['name']
    Track.save_broken_track(youtube_id, name)
    return Response()


@app.route('/stats')
def stats():
    """Render some stats about the application."""
    return render_template(
        'stats.html',
        artist_count=len(Artist.artists),
        tracks_count=len(Track.tracks),
    )


logging.basicConfig(level=logging.DEBUG)

if __name__ == '__main__':
    app.run(debug=True)
