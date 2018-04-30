from abc import ABCMeta, abstractmethod


class Plugin(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, core, *, loop=None):
        ...

    @abstractmethod
    async def start(self):
        ...

    @abstractmethod
    async def run(self):
        ...


class BackendPlugin(Plugin):
    pass


class MetadataPlugin(Plugin, metaclass=ABCMeta):
    @abstractmethod
    async def enrich(self, episode_info):
        ...


class SearchPlugin(Plugin, metaclass=ABCMeta):
    @abstractmethod
    async def search(self, episode_info):
        ...


class DownloadPlugin(Plugin, metaclass=ABCMeta):
    @abstractmethod
    def is_downloading(self, episode_info):
        ...

    @abstractmethod
    async def download(self, episodes_info, data):
        ...


class PreProcessingPlugin(Plugin, metaclass=ABCMeta):
    @abstractmethod
    async def process(self, files):
        ...


class PostProcessingPlugin(Plugin, metaclass=ABCMeta):
    @abstractmethod
    async def process(self, episodes_info, files):
        ...
