from __future__ import annotations

import io
import os
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Iterable
from contextlib import contextmanager
from enum import IntEnum, StrEnum
from sqlite3 import Cursor, OperationalError, connect
from typing import Callable, Generator
from uuid import uuid4


@contextmanager
def sqlite_db(fpath: str, replace=False) -> Generator[Db]:
    if fpath != ':memory:':
        if replace and os.path.exists(fpath):
            os.remove(fpath)
        if not os.path.exists(fpath):
            with open(fpath, 'wb'):
                pass
        os.chmod(fpath, 0o600)
    conn = connect(fpath, autocommit=False)
    # conn.enable_load_extension(True)
    # conn.load_extension(sqlite_icu.extension_path().replace('.so', ''))
    db = Db(conn)
    yield db
    db.close()
    conn.close()


ERRORS = (OperationalError,)


class Record:  # pylint: disable=too-many-instance-attributes
    title: str = ''
    url: str = ''  # unique
    tags: str = ''  # '#t1 #t2 ...'
    notes: str = ''

    uuid: str = ''  # primary key
    last_mod: int = 0  # time.time()
    created: int = 0  # time.time()
    deleted: int = 0  # time.time()

    names = ('title', 'url', 'tags', 'notes', 'uuid', 'last_mod', 'created', 'deleted')

    @staticmethod
    def create() -> Record:
        r = Record()
        r.uuid = str(uuid4())
        r.created = int(time.time())
        r.last_mod = r.created
        return r

    def as_dict(self) -> dict:
        return dict(
            zip(
                self.names,
                [
                    self.title,
                    self.url,
                    self.tags,
                    self.notes,
                    self.uuid,
                    self.last_mod,
                    self.created,
                    self.deleted,
                ],
            )
        )

    @staticmethod
    def from_tuple(t: tuple) -> Record:
        r = Record()
        (r.title, r.url, r.tags, r.notes, r.uuid, r.last_mod, r.created, r.deleted) = t
        return r


class MERGE(IntEnum):
    ERROR = 1
    SKIP = 2
    OK = 3


class EDIT(IntEnum):
    NONE = 0  # edit cancelled
    OK1 = 1  # does not conflict with any existing URLs
    OK2 = 2  # conflicts with some existing URLs
    ERROR = 3


class SORT(StrEnum):
    LAST_MOD = 'm'
    CREATED = 'c'
    TITLE = 't'
    URL = 'u'


class SORTED(IntEnum):
    NO = 0
    ASC = 1
    DESC = 2


def is_sorted(key: str, sort: SORT) -> SORTED:
    match key:
        case 'm':
            if sort == SORT.LAST_MOD:
                return SORTED.DESC
        case 'c':
            if sort == SORT.CREATED:
                return SORTED.DESC
        case 't':
            if sort == SORT.TITLE:
                return SORTED.ASC
        case 'u':
            if sort == SORT.URL:
                return SORTED.ASC
    return SORTED.NO


class Db:
    table_name = 'bookmarks'
    create_sql = f'''\
create table if not exists {table_name} (
    title text,
    url text,
    tags text,
    notes text,
    uuid text,          -- to store in memory
    last_mod integer,   -- time.time()
    created integer,    -- time.time()
    deleted integer,    -- time.time()
    constraint bm_uuid primary key (uuid),
    constraint bm_url unique (url)
);
create index if not exists bm_last_mod on {table_name} (last_mod desc);
create index if not exists bm_created on {table_name} (created desc);
create index if not exists bm_title on {table_name} (lower(title) asc, last_mod desc);
'''

    def __init__(self, conn):
        self.conn = conn
        self.cursors: deque[Cursor] = deque()
        self.error = None
        self._create_table()

    @contextmanager
    def _cursor(self):
        try:
            cur = self.cursors.pop()  # last unused cursor
        except IndexError:
            cur = self.conn.cursor()
        try:
            yield cur
        finally:
            self.cursors.append(cur)

    def close(self):
        try:
            while self.cursors:
                self.cursors.pop().close()
        except IndexError:
            pass

    def _create_table(self):
        with self._cursor() as cur:
            cur.executescript(self.create_sql)
            self.conn.commit()

    def get_by_field(self, name: str, value: str) -> Record | None:
        names_s = ', '.join(Record.names)
        sql = f'select {names_s} from {self.table_name} where {name} = :{name}'
        self.error = None
        with self._cursor() as cur:
            try:
                res = cur.execute(sql, {name: value})
                t = res.fetchone()
                if not t:
                    return None
                return Record.from_tuple(t)
            except ERRORS as e:
                self.error = e
        return None

    def get_by_uuid(self, uuid: str) -> Record | None:
        return self.get_by_field('uuid', uuid)

    def get_by_url(self, url: str) -> Record | None:
        return self.get_by_field('url', url)

    def insert(self, r: Record, commit: bool) -> bool:
        sql = insert_sql(self.table_name, Record.names)
        self.error = None
        with self._cursor() as cur:
            try:
                cur.execute(f'{sql}', r.as_dict())
                if commit:
                    self.conn.commit()
                return True
            except ERRORS as e:
                self.error = e
                self.conn.rollback()
        return False

    def update(self, r: Record, commit: bool) -> bool:
        sql = update_sql(self.table_name, Record.names)
        sql += ' where uuid = :uuid'
        self.error = None
        with self._cursor() as cur:
            try:
                cur.execute(sql, r.as_dict())
                if commit:
                    self.conn.commit()
                return True
            except ERRORS as e:
                self.error = e
                self.conn.rollback()
        return False

    def del_by_uuid(self, uuid: str, commit: bool) -> bool:
        sql = f'delete from {self.table_name} where uuid = :uuid'
        with self._cursor() as cur:
            try:
                cur.execute(sql, {'uuid': uuid})
                if commit:
                    self.conn.commit()
                return True
            except ERRORS as e:
                self.error = e
                self.conn.rollback()
        return False

    def mark_del(self, uuid: str, commit: bool) -> bool:
        r = self.get_by_uuid(uuid)
        if not r:
            return True
        if r.deleted:
            return self.del_by_uuid(uuid, commit)
        deleted = int(time.time())
        sql = f'update {self.table_name} set deleted = {deleted} where uuid = :uuid'
        with self._cursor() as cur:
            try:
                cur.execute(sql, {'uuid': uuid})
                if commit:
                    self.conn.commit()
                return True
            except ERRORS as e:
                self.error = e
                self.conn.rollback()
        return False

    def merge_record(self, r: Record) -> MERGE:
        # r - record from external source
        r2 = self.get_by_url(r.url)  # uuid is not relevant
        if r2:
            if r2.deleted > r.last_mod:
                return MERGE.SKIP
            if r2.last_mod < r.last_mod:
                # delete old r2
                if not self.del_by_uuid(r2.uuid, False):
                    return MERGE.ERROR
            else:
                # skip old r
                return MERGE.SKIP
        if not self.insert(r, True):
            return MERGE.ERROR
        return MERGE.OK

    def edit_record(self, r: Record) -> EDIT:
        try:
            return self._edit_record(r)
        except KeyboardInterrupt:
            return EDIT.NONE

    def _edit_record(self, r: Record) -> EDIT:  # pylint: disable=too-many-return-statements
        url = r.url
        if not edit_record(r):
            return EDIT.NONE
        r.last_mod = int(time.time())
        r.deleted = 0  # the only way to undo delete
        if url == r.url:
            # most cases
            if not self.update(r, True):
                return EDIT.ERROR
            return EDIT.OK1
        r2 = self.get_by_url(r.url)
        if not r2:
            # slightly altered URL
            if not self.update(r, True):
                return EDIT.ERROR
            return EDIT.OK1
        # rare case
        # r2 is older than r so delete it
        res = self.del_by_uuid(r2.uuid, False) and self.update(r, True)
        if not res:
            return EDIT.ERROR
        return EDIT.OK2

    def insert_record(self, r: Record) -> EDIT:
        try:
            return self._insert_record(r)
        except KeyboardInterrupt:
            return EDIT.NONE

    def _insert_record(self, r: Record) -> EDIT:
        if not edit_record(r):
            return EDIT.NONE
        r2 = self.get_by_url(r.url)
        if not r2:
            # most cases
            if not self.insert(r, True):
                return EDIT.ERROR
            return EDIT.OK1
        # rare case
        # r2 is older than r so delete it
        res = self.del_by_uuid(r2.uuid, False) and self.insert(r, True)
        if not res:
            return EDIT.ERROR
        return EDIT.OK2

    def sort(self, sort: SORT, deleted: bool) -> Generator[Record]:
        names_s = ', '.join(Record.names)
        sql = f'select {names_s} from {self.table_name}'
        if not deleted:
            sql += ' where deleted = 0'
        else:
            sql += ' where deleted != 0'
        match sort:
            case SORT.LAST_MOD:
                sql += ' order by last_mod desc'
            case SORT.CREATED:
                sql += ' order by created desc'
            case SORT.TITLE:
                sql += ' order by lower(title), last_mod desc'
            case SORT.URL:
                sql += ' order by url'
        self.error = None
        with self._cursor() as cur:
            try:
                for t in cur.execute(sql):
                    yield Record.from_tuple(t)
            except ERRORS as e:
                self.error = e


def edit_record(r: Record) -> bool:
    fd = None
    fpath = ''
    try:
        fd, fpath = tempfile.mkstemp(dir='/dev/shm', text=True)
        record2file(r, fpath)
        t1 = os.path.getmtime(fpath)
        subprocess.run(['vim', fpath], check=False)
        t2 = os.path.getmtime(fpath)
        if t1 != t2:
            file2record(fpath, r)  # r changed
            return True
    finally:
        if fd:
            os.close(fd)
            os.remove(fpath)
    return False


def file2record(fpath: str, r: Record):
    d = file2dict(fpath)
    r.url = d['url']
    r.title = d['title']
    r.tags = d['tags']
    r.notes = d['notes'].rstrip()


def file2dict(fpath: str) -> dict:
    with open(fpath, 'r', encoding='utf-8') as fp:
        return stream2dict(fp)


def stream2dict(fp) -> dict:
    steps = []
    for id_, s, _, type_ in FIELDS:
        steps.append((f'{s}:\n', id_, type_))
    d = {}
    step = 0
    read_value = 0
    for line in fp:
        s, id_, type_ = steps[step]
        if read_value == 1:
            d[id_] = line.rstrip()
            read_value = 0
            step += 1
            if step >= len(steps):
                break
            continue
        if read_value == 2:
            # read lines to the end
            d[id_] += line.rstrip() + '\r\n'
            continue
        if line != s:
            continue
        if id_ not in d:
            d[id_] = ''
        read_value = type_
    return d


def record2file(r: Record, fpath: str):
    with open(fpath, 'w', encoding='utf-8') as fp:
        record2stream(fp, r)


def notes2str(r: Record) -> str:
    s = ''
    if r.notes:
        s = r.notes.rstrip().replace('\r\n', '\n')
        s = s.replace('\t', ' ' * 4)
    return s


FIELDS: list[tuple[str, str, Callable[[Record], str], int]] = [
    # id, title, r -> str, type
    ('url', 'URL', lambda r: r.url, 1),
    ('title', 'Title', lambda r: r.title, 1),
    ('tags', 'Tags', lambda r: r.tags, 1),
    ('notes', 'Notes', notes2str, 2),
]


def record2str(r: Record) -> str:
    with io.StringIO() as fp:
        record2stream(fp, r)
        return fp.getvalue()


def record2stream(fp, r: Record):
    first = True
    for _, s, f, _ in FIELDS:
        if first:
            first = False
        else:
            fp.write('\n')
        fp.write(f'{s}:\n{f(r)}\n')


def names2vars(names: Iterable[str]) -> list[str]:
    return [f':{i}' for i in names]


def insert_sql(table: str, names: Iterable[str]) -> str:
    names_s = ', '.join(names)
    vars_s = ', '.join(names2vars(names))
    return f'insert into {table} ({names_s}) values ({vars_s})'


def update_sql(table: str, names: Iterable[str]) -> str:
    names_s = ', '.join(f'{name} = :{name}' for name in names)
    return f'update {table} set {names_s}'
