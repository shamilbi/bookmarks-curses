from datetime import datetime
from subprocess import PIPE, Popen


def int2time(i: int, format_: str) -> str:
    if not i:
        return ''
    return datetime.fromtimestamp(i).strftime(format_)


def str2clipboard(s: str):
    with Popen(['xsel', '-b', '-i'], stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True) as p:
        p.communicate(input=s)


class FilterString:
    def __init__(self):
        self.set()

    def set(self, s: str = ''):
        self.filter_string = s
        words = {i.lower() for i in s.split()}
        exclude_tags = {i for i in words if i.startswith('-#')}
        self.exclude_tags = {i[1:] for i in exclude_tags}
        self.words = words - exclude_tags

    def found(self, *fields: str, tags: str = '') -> bool:
        if not self.filter_string:
            return True
        low_fields = {i.lower() for i in fields}
        if tags:
            low_fields.add(tags.lower())
            words = {i.lower() for i in tags.split()}
            if any(i in words for i in self.exclude_tags):
                return False
        return all(any(f2.find(s) >= 0 for f2 in low_fields) for s in self.words)
