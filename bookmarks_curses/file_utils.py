import os
import subprocess
from contextlib import contextmanager
from typing import Generator


def fill_by_0(fpath):
    "dd if=/dev/zero of=<file> conv=notrunc bs=<size> count=1"
    size = os.path.getsize(fpath)
    if size:
        subprocess.run(
            ['dd', 'if=/dev/zero', f'of={fpath}', 'conv=notrunc', f'bs={size}', 'count=1'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@contextmanager
def create_memfd(name) -> Generator[tuple[int, str]]:
    """
    Create an anonymous file in memory.
    os.memfd_create + close
    Availability: Linux >= 3.17 with glibc >= 2.27, python >= 3.8
    """
    fd = os.memfd_create(name)
    # fpath = f'/proc/self/fd/{fd}'  # permission denied
    fpath = f'/proc/{os.getpid()}/fd/{fd}'
    try:
        os.chmod(fd, 0o600)
        yield (fd, fpath)
    finally:
        os.close(fd)


@contextmanager
def create_memfd2(name) -> Generator[tuple[int, str]]:
    "create_memfd + fill by zero + truncate"
    with create_memfd(name) as (fd, fpath):
        try:
            yield (fd, fpath)
        finally:
            fill_by_0(fpath)
            os.truncate(fd, 0)
