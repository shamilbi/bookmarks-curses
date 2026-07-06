import glob
import os
import readline
import subprocess
from contextlib import contextmanager
from functools import lru_cache
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


@lru_cache(maxsize=1)
def _glob_text(text: str):
    l = glob.glob(os.path.expanduser(text) + '*')
    # dir -> dir/
    for i, s in enumerate(l):
        if s and os.path.isdir(s) and not s.endswith('/'):
            l[i] = s + '/'
    return l


def _complete(text: str, state: int):
    'https://stackoverflow.com/questions/6656819/filepath-autocompletion-using-users-input'
    # return (glob.glob(text+'*')+[None])[state]
    # return (glob.glob(os.path.expanduser(text) + '*') + [None])[state]
    return (_glob_text(text) + [None])[state]


def input_file(prompt: str):
    readline.set_completer_delims(' \t\n;')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(_complete)
    while True:
        s = input(f'{prompt}')
        s = s.strip()
        if not s:
            continue
        s = os.path.expanduser(s)  # ~/filename
        if os.path.isfile(s) or not os.path.exists(s):
            return s
        print(f'{s} is not a file')
