# from getpass import getpass
import glob
import os
import readline
from datetime import datetime
from functools import lru_cache
from subprocess import PIPE, Popen
from typing import Generator


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


def int2time(i: int) -> str:
    if not i:
        return ''
    return datetime.fromtimestamp(i).strftime('%Y-%m-%d %H:%M:%S')


def chunkstring(s: str, chunk_len: int) -> Generator[str]:
    len_ = len(s)
    i = 0
    while True:
        yield s[i : i + chunk_len]  # works even if s=''
        i += chunk_len
        if not i < len_:
            break


class RowString:
    '{value1:<width1} {value2:<width2} ...'

    def __init__(self, *widths: int):
        self.widths = widths

    def value(self, *values: str):
        # min_ = min(len(self.widths), len(values))
        s = ''
        for w, v in zip(self.widths, values):
            if not w:
                # last value
                s += v
            else:
                s += f'{v[:w]:<{w}} '
        s = s.rstrip()  # last item stripped
        return s


def str2clipboard(s: str):
    with Popen(['xsel', '-b', '-i'], stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True) as p:
        p.communicate(input=s)


class FilterString:
    def __init__(self):
        self.set()

    def set(self, s: str = ''):
        self.filter_string = s
        self.filter_list = [i.lower() for i in self.filter_string.split()]

    def found(self, *fields: str) -> bool:
        if not self.filter_string:
            return True
        fields2 = [i.lower() for i in fields]
        return all(any(f2.find(s) >= 0 for f2 in fields2) for s in self.filter_list)
