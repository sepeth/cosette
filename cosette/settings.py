"""Settings entry point, envs are sanitized in this module for the rest of the app."""
import os

REDIS_HOST = os.environ['COSETTE_REDIS_HOST']
REDIS_DB = int(os.environ.get('COSETTE_REDIS_DB', 0))
LASTFM_API_KEY = os.environ['COSETTE_LASTFM_API_KEY']
YOUTUBE_API_KEY = os.environ['COSETTE_YOUTUBE_API_KEY']
