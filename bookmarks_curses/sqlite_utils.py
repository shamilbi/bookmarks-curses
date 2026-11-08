from __future__ import annotations

import os
import sqlite3
from abc import abstractmethod
from collections import deque
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from enum import IntEnum
from sqlite3 import Connection, Cursor, IntegrityError, OperationalError
from typing import Protocol, Self

from curses_utils2.record import RecordProto, edit_record

type DbError = OperationalError | IntegrityError
ERRORS = (OperationalError, IntegrityError)


@contextmanager
def connect(fpath: str, replace=False) -> Generator[Connection]:
    if fpath != ':memory:':
        if replace and os.path.exists(fpath):
            os.remove(fpath)
        if not os.path.exists(fpath):
            with open(fpath, 'wb'):
                pass
        os.chmod(fpath, 0o600)

    # autocommit=False
    # https://sqlite.org/foreignkeys.html
    # It is not possible to enable or disable foreign key constraints in the middle of a multi-statement transaction
    # (when SQLite is not in autocommit mode).
    # Attempting to do so does not return an error; it simply has no effect.

    conn = sqlite3.connect(fpath, autocommit=True)
    conn.execute("PRAGMA foreign_keys=1")
    # conn.enable_load_extension(True)
    # conn.load_extension(sqlite_icu.extension_path().replace('.so', ''))
    try:
        yield conn
    finally:
        conn.close()


class DbProto(Protocol):
    error: str | None

    @contextmanager
    def cursor(self) -> Generator[Cursor]:
        pass


class SqliteDb(DbProto):
    conn: Connection
    cursors: deque[Cursor]  # unused cursors

    def __init__(self, conn: Connection):
        self.conn = conn
        self.cursors = deque()
        self.error = None

    @contextmanager
    def cursor(self) -> Generator[Cursor]:
        '''
        with cursor() as cur:
            ...
        '''
        if self.cursors:
            cur: Cursor = self.cursors.pop()  # last unused cursor
        else:
            cur = self.conn.cursor()
        try:
            yield cur
        finally:
            self.cursors.append(cur)

    def close(self):
        while self.cursors:
            self.cursors.pop().close()


def list_tables(db: DbProto) -> Generator[str]:
    'all existing tables'
    with db.cursor() as cur:
        res = cur.execute('select name from sqlite_master where type = "table"')
        while t := res.fetchone():
            yield t[0]


def names2str(names: Iterable[str], prefix: str = '') -> str:
    '(name1, name2, ...) -> name1, name2, ...'
    if not prefix:
        return ', '.join(names)
    return ', '.join(f'{prefix}.{i}' for i in names)


def names2vars(names: Iterable[str]) -> list[str]:
    'i -> :i'
    return [f':{i}' for i in names]


def insert_sql(table: str, names: Iterable[str]) -> str:
    names_s = names2str(names)
    vars_s = ', '.join(names2vars(names))
    return f'insert into {table} ({names_s}) values ({vars_s})'


def update_sql(table: str, names: Iterable[str]) -> str:
    'i, j -> i = :i, j = :j'
    names_s = ', '.join(f'{name} = :{name}' for name in names)
    return f'update {table} set {names_s}'


class DbRecordProto(RecordProto):
    names: tuple[str, ...]
    table_name: str
    error: str | None = None

    @abstractmethod
    def set_tuple(self, t: tuple):
        pass

    @abstractmethod
    def as_dict(self) -> dict:
        pass

    def from_tuple(self, t: tuple) -> Self:
        r = self.__class__()
        r.set_tuple(t)
        return r

    def insert(self, db: DbProto) -> bool:
        sql = insert_sql(self.table_name, self.names)
        db.error = None
        with db.cursor() as cur:
            try:
                cur.execute(sql, self.as_dict())
                return True
            except ERRORS as e:
                db.error = str(e)
        return False


class IdRecordProto(DbRecordProto):
    id: int = 0
    id_name: str

    @abstractmethod
    def set_tuple(self, t: tuple):
        pass

    @abstractmethod
    def set_dict(self, d: dict) -> bool:
        pass

    @abstractmethod
    def as_dict(self) -> dict:
        pass

    def names_wo_id(self) -> Iterable[str]:
        names = list(self.names)
        names.remove(self.id_name)
        return names

    def dict_wo_id(self) -> dict:
        d = self.as_dict()
        del d[self.id_name]
        return d

    def insert(self, db: DbProto) -> bool:
        names_s = ', '.join(self.names)
        sql = f'{insert_sql(self.table_name, self.names_wo_id())} returning {names_s}'
        db.error = None
        with db.cursor() as cur:
            try:
                res = cur.execute(sql, self.dict_wo_id())
                self.set_tuple(res.fetchone())
                return True
            except ERRORS as e:
                db.error = str(e)
        return False

    def update(self, db: DbProto) -> bool:
        sql = update_sql(self.table_name, self.names_wo_id())
        sql += f' where {self.id_name} = :{self.id_name}'
        db.error = None
        with db.cursor() as cur:
            try:
                cur.execute(sql, self.as_dict())
                return True
            except ERRORS as e:
                db.error = str(e)
        return False

    def delete(self, db: DbProto) -> bool:
        sql = f'delete from {self.table_name} where {self.id_name} = :{self.id_name}'
        db.error = None
        with db.cursor() as cur:
            try:
                cur.execute(sql, {self.id_name: self.id})
                return True
            except ERRORS as e:
                db.error = str(e)
        return False

    def get_by_id(self, id_: int, db: DbProto) -> Self | None:
        names_s = ', '.join(self.names)
        id_name = self.id_name
        sql = f'select {names_s} from {self.table_name} where {id_name} = :{id_name}'
        db.error = None
        with db.cursor() as cur:
            try:
                res = cur.execute(sql, {id_name: id_})
                t = res.fetchone()
                if not t:
                    return None
                return self.from_tuple(t)
            except ERRORS as e:
                db.error = str(e)
        return None

    def insert_record(self, db: DbProto, comment: str = '') -> EDIT:
        try:
            if not edit_record(self, comment=comment):
                if self.error:
                    db.error = self.error
                    return EDIT.ERROR
                return EDIT.NONE
            if not self.insert(db):
                return EDIT.ERROR
            return EDIT.OK
        except KeyboardInterrupt:
            return EDIT.NONE

    def edit_record(self, db: DbProto, comment: str = '') -> EDIT:
        try:
            if not edit_record(self, comment=comment):
                if self.error:
                    db.error = self.error
                    return EDIT.ERROR
                return EDIT.NONE
            if not self.update(db):
                return EDIT.ERROR
            return EDIT.OK
        except KeyboardInterrupt:
            return EDIT.NONE


class EDIT(IntEnum):
    NONE = 0  # edit cancelled
    OK = 1
    ERROR = 2
