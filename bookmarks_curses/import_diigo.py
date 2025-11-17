import io
import os
import re
from collections import deque

from .db import MERGE, Db, Record
from .utils import input_file


class Import:
    ok: bool = False
    error: str = ''
    line: int = 0
    added: int = 0
    skipped: int = 0

    def __bool__(self):
        return self.ok


def import_html(db: Db) -> Import:
    res = Import()
    try:
        while True:
            fpath = input_file('html file: ')
            if not os.path.exists(fpath):
                print('file not exist')
                continue
            if not os.path.isfile(fpath):
                print('not file')
                continue
            if not fpath.lower().endswith('.html'):
                print('not html file')
                continue
            break
        res = import_html_dp(db, fpath)
    except KeyboardInterrupt:
        pass
    return res


def import_html_dp(db: Db, fpath: str) -> Import:
    res = Import()
    with open(fpath, 'r', encoding='utf-8') as fp:
        import_html2(db, res, fp)
    return res


def import_html2(db: Db, res: Import, fp: io.TextIOBase):  # pylint: disable=too-many-branches
    rq: deque[Record] = deque()  # last record to insert

    def check_prev_record() -> bool:
        if rq:
            r = rq.pop()
            r.notes = r.notes.rstrip()
            match db.merge_record(r):
                case MERGE.ERROR:
                    res.error = 'merge error'
                    return False
                case MERGE.SKIP:
                    res.skipped += 1
                    return True
                case MERGE.OK:
                    res.added += 1
                    return True
        return True

    def is_a(line: str) -> bool:
        # <DT><A HREF="..." LAST_VISIT="1761579546" ADD_DATE="1761579546" PRIVATE="0" TAGS="fun,db">...title...</A>
        # return line.startswith('<DT><A ') and line.endswith('</A>')
        return line.startswith('<DT><A ')

    def is_eof(line: str) -> bool:
        return line.startswith('</DL>')

    def next_record(line: str) -> Record | None:
        if check_prev_record():
            r, ok = dt2record(line, res)
            if ok:
                rq.append(r)
                return r
        return None

    step = 0
    for line in fp:
        line = line.rstrip()
        res.line += 1
        match step:
            case 0:
                if not is_a(line):
                    continue
                r = next_record(line)
                if not r:
                    break
                step = 1
            case 1:
                # <DD>...
                if line.startswith('<DD>'):
                    r.notes = f'{line[4:]}\n'  # type: ignore[union-attr]
                    step = 2
                    continue
                if not is_a(line):
                    # </DL><p>
                    if is_eof(line):
                        # end of file
                        continue
                    res.error = 'bad line'
                    break
                r = next_record(line)
                if not r:
                    break
                step = 1
            case 2:
                # append to notes
                if not is_a(line):
                    # </DL><p>
                    if is_eof(line):
                        # end of file
                        continue
                    r.notes += f'{line}\n'  # type: ignore[union-attr]
                    continue
                r = next_record(line)
                if not r:
                    break
                step = 1
    else:
        if not check_prev_record():
            return
        res.ok = True


def dt2record(line: str, res: Import) -> tuple[Record, bool]:
    r = Record.create()
    m = re.search(r' HREF="([^"]*)" ', line)
    if not m:
        res.error = 'HREF not found'
        return (r, False)
    r.url = m.group(1)

    m = re.search(r' LAST_VISIT="([0-9]+)" ', line)
    if not m:
        res.error = 'LAST_VISIT not found'
        return (r, False)
    r.last_mod = int(m.group(1))

    m = re.search(r' ADD_DATE="([0-9]+)" ', line)
    if not m:
        res.error = 'ADD_DATE not found'
        return (r, False)
    r.created = int(m.group(1))

    m = re.search(r' TAGS="([^"]*)">', line)
    if not m:
        res.error = 'TAGS not found'
        return (r, False)
    # tags: #tag1 #tag2 ...
    r.tags = ' '.join(f'#{i}' for i in m.group(1).split(',') if i)

    m = re.search(r'">(.*)</A>', line)
    if not m:
        res.error = 'A-body not found'
        return (r, False)
    r.title = m.group(1).strip()
    r.title = r.title.lstrip('‎')

    return (r, True)
