from setuptools import setup, find_packages


requires = [
    'cached_property',
    'google-api-python-client',
    'redis',
    'hiredis',
    'requests',
    'flask',
    'gevent',
]


setup(
    name='cosette',
    version='0.1',
    description='Find One Hit Wonders',
    url='https://github.com/sepeth/cosette',
    author='Doğan Çeçen',
    author_email='sepeth@gmail.com',
    install_requires=requires,
    packages=find_packages(),
)
