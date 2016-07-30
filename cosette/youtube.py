"""Youtube related stuff, it abstracts the requests sent to youtube."""
from apiclient.discovery import build  # pylint: disable=import-error
from cosette import settings


YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


def search(**options):
    """Search song in youtube with the given options"""
    youtube = build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        developerKey=settings.YOUTUBE_API_KEY
    )
    resp = youtube.search().list(
        q=options['q'],
        type='video',
        part='id,snippet',
        videoEmbeddable='true'
    ).execute()
    return resp.get('items', [])
