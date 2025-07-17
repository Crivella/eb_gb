"""Implement an hash based file storage system for Django."""
import gzip
import hashlib
import os

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils._os import safe_join
from django.utils.deconstruct import deconstructible

try:
    from disk_objectstore import Container
except ImportError:
    Container = None


@deconstructible
class HashStorage(FileSystemStorage):
    """
    A custom storage system that hashes file names to avoid collisions.
    """
    def __init__(self, compression=None, **kwargs):
        super().__init__(**kwargs)
        self.compression = compression

    def get_available_name(self, name, max_length=None):
        """Return the original filename, the real one is generated based on the content."""
        return name[:max_length]

    @staticmethod
    def get_md5(content: File):
        """Generate an MD5 hash of the content."""
        md5 = hashlib.md5()
        content.seek(0)
        for chunk in content.chunks():
            md5.update(chunk)
        content.seek(0)
        return md5.hexdigest()

    @staticmethod
    def get_shards(hash_str: str) -> str:
        """Generate a sharded name based on the MD5 hash of the content."""
        shard1 = hash_str[:2]
        shard2 = hash_str[2:4]
        shard3 = hash_str[4:]

        return os.path.join(shard1, shard2, shard3)

    def path(self, name: str) -> str:
        """Return the full path to the file."""
        return safe_join(self.location, self.get_shards(name))

    def url(self, name: str) -> str:
        """Return the URL to the file."""
        return super().url(self.get_shards(name))

    def _open(self, name: str, mode='rb') -> File:
        """Open the file with gzip if compression is enabled."""
        full_path = self.path(name)
        if self.compression == 'gzip':
            return File(gzip.open(full_path, mode))
        return super()._open(name, mode)

    def _save(self, name: str, content: File) -> str:
        """Save the file with a hashed name."""
        hash_str = self.get_md5(content)
        full_path = self.path(hash_str)

        if os.path.exists(full_path):
            # If the file already exists, return the existing hash
            return hash_str

        if self.compression == 'gzip':
            with content.open('rb') as f_in:
                data = f_in.read()
            content = ContentFile(gzip.compress(data), name=name)

        super()._save(hash_str, content)
        return hash_str

@deconstructible
class DOSStorage(Storage):
    """
    A custom storage making use of aiidateam/disk-objectstore.
    """
    def __init__(self, location=None):
        if Container is None:
            raise ImportError('disk-objectstore is not installed. Please install it to use DOSStorage.')
        self.location = os.path.abspath(location)

        self.container = Container(os.path.join(self.location, 'disk_objectstore'))
        if not self.container.is_initialised:
            self.container.init_container()

    def exists(self, name: str) -> bool:
        """Check if the file exists in the storage."""
        return self.container.has_object(name)

    def get_accessed_time(self, name):
        """Get the last accessed time of the file."""
        raise NotImplementedError('Accessed time is not supported in DOSStorage.')

    def get_created_time(self, name):
        """Get the creation time of the file."""
        raise NotImplementedError('Created time is not supported in DOSStorage.')

    def get_modified_time(self, name):
        """Get the last modified time of the file."""
        raise NotImplementedError('Modified time is not supported in DOSStorage.')

    def listdir(self, path):
        """List directories and files in the given path."""
        raise NotImplementedError('Listing directories is not supported in DOSStorage.')

    def size(self, name: str) -> int:
        """Get the size of the file."""
        if not self.exists(name):
            raise FileNotFoundError(f"File '{name}' does not exist.")
        with self.container as container:
            return container.get_object_meta(name).size

    def delete(self, name: str):
        """Delete the file from the storage."""
        raise NotImplementedError('Deletion is not supported in DOSStorage.')

    def url(self, name: str) -> str:
        """Return the URL to access the file."""
        raise NotImplementedError('URL access is not supported in DOSStorage.')

    def get_available_name(self, name, max_length=None):
        """Return the original filename, the real one is generated based on the content."""
        return name[:max_length]

    def _open(self, name: str, mode='rb') -> File:  # pylint: disable=unused-argument
        """Open the file with gzip if compression is enabled."""
        with self.container as container:
            content = container.get_object_content(name)
        return ContentFile(content, name=name)

    def _save(self, name: str, content: File) -> str:  # pylint: disable=unused-argument
        """Save the file with a hashed name."""
        res = None
        try:
            with self.container as container:
                res = container.add_streamed_object(content)
        finally:
            content.close()
        return res
