"""Lastfm related functions."""
import requests
from cosette import settings


API_URL = ('http://ws.audioscrobbler.com/2.0/'
           '?method={method}&api_key={api_key}&format=json')


def call_api(method, **kwargs):
    """Call method of lastfm api with the given params."""
    url = API_URL.format(api_key=settings.LASTFM_API_KEY, method=method)
    resp = requests.get(url, params=kwargs)
    return resp.json()
