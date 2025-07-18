"""Implement an hash based file storage system for Django."""
import os

from disk_objectstore import Container
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


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
