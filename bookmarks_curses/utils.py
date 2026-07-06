from datetime import datetime
from subprocess import PIPE, Popen
from typing import Generator


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
        words = set(i.lower() for i in s.split())
        exclude_tags = set(i for i in words if i.startswith('-#'))
        self.exclude_tags = set(i[1:] for i in exclude_tags)
        self.words = words - exclude_tags

    def found(self, *fields: str, tags: str = '') -> bool:
        if not self.filter_string:
            return True
        low_fields = set(i.lower() for i in fields)
        if tags:
            low_fields.add(tags.lower())
            words = set(i.lower() for i in tags.split())
            if any(i in words for i in self.exclude_tags):
                return False
        return all(any(f2.find(s) >= 0 for f2 in low_fields) for s in self.words)
