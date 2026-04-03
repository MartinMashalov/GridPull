"""Hetzner Storage Box via SFTP (paramiko)."""

import asyncio
import logging
import posixpath

import paramiko

from app.config import settings

logger = logging.getLogger(__name__)

_transport = None
_sftp = None


def _get_sftp() -> paramiko.SFTPClient:
    """Return a reusable SFTP client, reconnecting if needed."""
    global _transport, _sftp
    if _transport is None or not _transport.is_active():
        _transport = paramiko.Transport((settings.storagebox_host, settings.storagebox_port))
        _transport.connect(username=settings.storagebox_username, password=settings.storagebox_password)
        _sftp = paramiko.SFTPClient.from_transport(_transport)
        logger.info("SFTP connected to %s:%d", settings.storagebox_host, settings.storagebox_port)
    return _sftp


def _mkdirs(sftp: paramiko.SFTPClient, remote_dir: str):
    """Recursively create remote directories if they don't exist."""
    dirs_to_create = []
    current = remote_dir
    while current and current != "/":
        try:
            sftp.stat(current)
            break
        except FileNotFoundError:
            dirs_to_create.append(current)
            current = posixpath.dirname(current)
    for d in reversed(dirs_to_create):
        try:
            sftp.mkdir(d)
        except IOError:
            pass  # already exists (race condition)


async def upload_file(
    user_id: str,
    doc_id: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str:
    """Upload bytes to storage box, return the storage key (remote path)."""
    base = settings.storagebox_base_path.rstrip("/")
    storage_key = f"{user_id}/{doc_id}/{filename}"
    remote_path = f"{base}/{storage_key}"
    remote_dir = posixpath.dirname(remote_path)

    def _put():
        import io
        sftp = _get_sftp()
        _mkdirs(sftp, remote_dir)
        with sftp.open(remote_path, "wb") as f:
            f.write(data)

    await asyncio.to_thread(_put)
    logger.info("SFTP upload: %s (%d bytes)", storage_key, len(data))
    return storage_key


async def download_file(storage_key: str) -> bytes:
    """Download a file and return its bytes."""
    base = settings.storagebox_base_path.rstrip("/")
    remote_path = f"{base}/{storage_key}"

    def _get():
        import io
        sftp = _get_sftp()
        with sftp.open(remote_path, "rb") as f:
            return f.read()

    data = await asyncio.to_thread(_get)
    logger.info("SFTP download: %s (%d bytes)", storage_key, len(data))
    return data


async def delete_file(storage_key: str) -> None:
    """Delete a single file."""
    base = settings.storagebox_base_path.rstrip("/")
    remote_path = f"{base}/{storage_key}"

    def _del():
        sftp = _get_sftp()
        try:
            sftp.remove(remote_path)
        except FileNotFoundError:
            pass
        # Try to clean up empty parent dirs
        parent = posixpath.dirname(remote_path)
        for _ in range(2):  # up to 2 levels (doc_id dir, user_id dir)
            try:
                sftp.rmdir(parent)
                parent = posixpath.dirname(parent)
            except (IOError, OSError):
                break

    await asyncio.to_thread(_del)
    logger.info("SFTP delete: %s", storage_key)


async def delete_many_files(storage_keys: list[str]) -> None:
    """Delete multiple files."""
    if not storage_keys:
        return

    def _batch_del():
        sftp = _get_sftp()
        base = settings.storagebox_base_path.rstrip("/")
        for key in storage_keys:
            remote_path = f"{base}/{key}"
            try:
                sftp.remove(remote_path)
            except FileNotFoundError:
                pass

    await asyncio.to_thread(_batch_del)
    logger.info("SFTP batch delete: %d files", len(storage_keys))
