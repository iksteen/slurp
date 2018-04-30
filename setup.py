import os
from setuptools import setup, find_packages

requires = [
    'appdirs',
    'guessit',
    'rarfile',
    'bencoder',
    'aiohttp',
    'click',
    'python-dateutil',
    'requests',
    'babelfish',
    'defusedxml',
    'pyrencode',
    'cidict',
    'asyncpg',
    'beautifulsoup4',
    'lxml',
]


here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()

setup(
    name='slurp',
    version='0.9.0',
    description='Automatic TV show download orchestrator',
    long_description=README,
    author='Ingmar Steen',
    author_email='iksteen@gmail.com',
    url='https://github.com/iksteen/slurp',
    license='MIT',
    packages=find_packages(),
    python_requires='>=3.5',
    install_requires=requires,
    entry_points={
        'console_scripts': [
            'slurp = slurp.__main__:main'
        ],
        'slurp.plugins.backend': [
            'trakt = slurp.plugins.trakt:TraktBackendPlugin',
        ],
        'slurp.plugins.metadata': [
            'tvdb = slurp.plugins.tvdb:TheTVDBMetadataPlugin',
            'scene_names = slurp.plugins.scene_names:SceneNamesMetadataPlugin',
        ],
        'slurp.plugins.search': [
            'torrentleech = slurp.plugins.torrentleech:TorrentLeechSearchPlugin',
            '1337x = slurp.plugins.1337x:LeetXSearchPlugin',
        ],
        'slurp.plugins.download': [
            'deluge_rpc = slurp.plugins.deluge_rpc:DelugeRpcDownloadPlugin',
        ],
        'slurp.plugins.processing': [
            'unrar = slurp.plugins.unrar:UnrarProcessingPlugin',
            'rename = slurp.plugins.rename:RenameProcessingPlugin',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: AsyncIO',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Internet',
        'Topic :: Multimedia :: Video',
        'Topic :: Utilities',
    ]
)
