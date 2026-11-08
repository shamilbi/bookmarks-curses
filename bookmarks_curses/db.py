from __future__ import annotations

import time
from collections.abc import Generator, Iterable
from enum import IntEnum, StrEnum
from typing import Self
from uuid import uuid4

from curses_utils2.record import Text2Field, edit_record

from .sqlite_utils import EDIT, ERRORS, DbProto, DbRecordProto, update_sql

TABLE_NAME = 'bookmarks'
CREATE_SQL = f'''\
create table if not exists {TABLE_NAME} (
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
create index if not exists bm_last_mod on {TABLE_NAME} (last_mod desc);
create index if not exists bm_created on {TABLE_NAME} (created desc);
create index if not exists bm_title on {TABLE_NAME} (lower(title) asc, last_mod desc);
'''


class Record(DbRecordProto):  # pylint: disable=too-many-instance-attributes
    names = ('title', 'url', 'tags', 'notes', 'uuid', 'last_mod', 'created', 'deleted')
    table_name = TABLE_NAME

    title: str = ''
    url: str = ''  # unique
    tags: str = ''  # '#t1 #t2 ...'
    notes: str = ''

    uuid: str = ''  # primary key
    last_mod: int = 0  # time.time()
    created: int = 0  # time.time()
    deleted: int = 0  # time.time()

    def __init__(self):
        super().__init__()
        self.uuid = str(uuid4())
        self.created = int(time.time())
        self.last_mod = self.created

    def form_fields(self) -> Iterable[tuple[str, str, str, Text2Field]]:
        'id, title, value, type'
        yield ('url', 'URL', self.url, Text2Field.SINGLE)
        yield ('title', 'Title', self.title, Text2Field.SINGLE)
        yield ('tags', 'Tags', self.tags, Text2Field.SINGLE)
        yield ('notes', 'Notes', self.notes, Text2Field.MULTI)

    def set_dict(self, d: dict) -> bool:
        for name, value in d.items():
            match name:
                case 'url':
                    self.url = value
                case 'title':
                    self.title = value
                case 'tags':
                    self.tags = value
                case 'notes':
                    self.notes = value
        return True

    def set_tuple(self, t: tuple):
        [
            self.title,
            self.url,
            self.tags,
            self.notes,
            self.uuid,
            self.last_mod,
            self.created,
            self.deleted,
        ] = t

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

    def get_by_field(self, db: DbProto, name: str, value: str) -> Self | None:
        names_s = ', '.join(self.names)
        sql = f'select {names_s} from {self.table_name} where {name} = :{name}'
        db.error = None
        with db.cursor() as cur:
            try:
                res = cur.execute(sql, {name: value})
                t = res.fetchone()
                if not t:
                    return None
                return self.from_tuple(t)
            except ERRORS as e:
                db.error = str(e)
        return None

    def get_by_uuid(self, db: DbProto, uuid: str) -> Self | None:
        return self.get_by_field(db, 'uuid', uuid)

    def get_by_url(self, db: DbProto, url: str) -> Self | None:
        return self.get_by_field(db, 'url', url)

    def update(self, db: DbProto) -> bool:
        sql = update_sql(self.table_name, self.names)
        sql += ' where uuid = :uuid'
        db.error = None
        with db.cursor() as cur:
            try:
                cur.execute(sql, self.as_dict())
                return True
            except ERRORS as e:
                db.error = str(e)
        return False

    def del_by_uuid(self, db: DbProto, uuid: str) -> bool:
        sql = f'delete from {self.table_name} where uuid = :uuid'
        with db.cursor() as cur:
            try:
                cur.execute(sql, {'uuid': uuid})
                return True
            except ERRORS as e:
                db.error = str(e)
        return False

    def mark_del(self, db: DbProto, uuid: str) -> bool:
        r = self.get_by_uuid(db, uuid)
        if not r:
            return True
        if r.deleted:
            return self.del_by_uuid(db, uuid)
        deleted = int(time.time())
        sql = f'update {self.table_name} set deleted = {deleted} where uuid = :uuid'
        with db.cursor() as cur:
            try:
                cur.execute(sql, {'uuid': uuid})
                return True
            except ERRORS as e:
                db.error = str(e)
        return False

    def merge_record(self, db: DbProto) -> MERGE:
        # self is not in DB, trying to insert
        r2 = self.get_by_url(db, self.url)  # uuid is not relevant
        if r2:
            if r2.deleted > self.last_mod:
                return MERGE.SKIP
            if r2.last_mod < self.last_mod:
                # delete old r2
                if not self.del_by_uuid(db, r2.uuid):
                    return MERGE.ERROR
            else:
                # skip old self
                return MERGE.SKIP
        if not self.insert(db):
            return MERGE.ERROR
        return MERGE.OK

    def edit_record(self, db: DbProto) -> EDIT:  # pylint: disable=too-many-return-statements
        url = self.url
        if not edit_record(self):
            return EDIT.NONE
        self.last_mod = int(time.time())
        self.deleted = 0  # the only way to undo delete
        if url == self.url:
            # most cases
            if not self.update(db):
                return EDIT.ERROR
            return EDIT.OK
        r2 = self.get_by_url(db, self.url)
        if not r2:
            # slightly altered URL
            if not self.update(db):
                return EDIT.ERROR
            return EDIT.OK
        # rare case
        # r2 is older than self so delete it
        res = self.del_by_uuid(db, r2.uuid) and self.update(db)
        if not res:
            return EDIT.ERROR
        return EDIT.OK

    def insert_record(self, db: DbProto) -> EDIT:
        'empty record -> edit -> insert'
        if not edit_record(self):
            return EDIT.NONE
        r2 = self.get_by_url(db, self.url)
        if not r2:
            # most cases
            if not self.insert(db):
                return EDIT.ERROR
            return EDIT.OK
        # rare case
        # r2 is older than r so delete it
        res = self.del_by_uuid(db, r2.uuid) and self.insert(db)
        if not res:
            return EDIT.ERROR
        return EDIT.OK

    def sort(self, db: DbProto, sort: SORT, deleted: bool) -> Generator[Record]:
        names_s = ', '.join(self.names)
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
        db.error = None
        with db.cursor() as cur:
            try:
                for t in cur.execute(sql):
                    yield self.from_tuple(t)
            except ERRORS as e:
                db.error = str(e)


class MERGE(IntEnum):
    ERROR = 1
    SKIP = 2
    OK = 3


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


def create_tables(db: DbProto):
    with db.cursor() as cur:
        cur.executescript(CREATE_SQL)
