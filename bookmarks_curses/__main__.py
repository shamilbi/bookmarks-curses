import curses
import curses.ascii
import os
import shutil
import subprocess
import webbrowser
from functools import partial
from typing import Generator

from . import __version__
from .curses_utils import App, ask_delete, escape2terminal, input_search, win_addstr, win_help
from .curses_utils.list3 import List3, ListProto3
from .db import (
    EDIT,
    SORT,
    SORTED,
    Db,
    Record,
    is_sorted,
    record2str,
    sqlite_db,
)
from .import_diigo import import_html
from .utils import (
    FilterString,
    RowString,
    chunkstring,
    input_file,
    int2time,
    str2clipboard,
)

APP_HEADER = f'bookmarks-curses v{__version__} (h - Help)'

HELP = [
    ("h", "This help screen"),
    ("q, Esc", "Quit the program"),
    ("j, Down", "Move selection down"),
    ("k, Up", "Move selection up"),
    ("PgUp", "Page up"),
    ("PgDown", "Page down"),
    ("g, Home", "Move to first item"),
    ("G, End", "Move to last item"),
    ("Alt-{m,c,t,u}", "Sort by modtime, created, title, URL"),
    ("Delete", "Delete current record"),
    ("Insert", "Insert record"),
    ("e", "Edit current record"),
    ("L", "Launch URL"),
    ("I", "Import html (Diigo export Chrome)"),
    ("s", "Search records"),
    ("D", "Show/hide deleted records"),
    ("U", "Show URL as QR-code"),
    ("Ctrl-L", "Copy URL to clipboard"),
    ("Ctrl-T", "Copy Title to clipboard"),
]

HEADER_KEYS = ('t', 'm', 'c', 'u')
HEADER: dict[str, str] = dict(zip(HEADER_KEYS, ('Title', 'ModTime', 'Created', 'URL')))

SORT_UP = '\u2191'
SORT_DOWN = '\u2193'


class Main(App, ListProto3):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    def __init__(self, db: Db, screen):
        super().__init__(screen)

        self.db = db

        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)

        self.records: list[str] = []  # uuid
        self.filter = FilterString()
        self.show_deleted = False
        self.sort(SORT.LAST_MOD)

        # title, last_mod, created, tags
        self.row_string = RowString(70, 19, 19, 0)  # title, last_mod, created, url
        self.row_string2 = RowString(4, 70 - 4)  # indent, tags

        self.create_windows()

    def sort(self, sortby: SORT):
        self.sortedby = sortby
        self.records = [r.uuid for r in self.db.sort(sortby, self.show_deleted) if self.filter_record(r)]

    def sort2(self, sortby: SORT):
        idx = self.win.idx
        uuid = None
        if idx < self.records_len():
            uuid = self.records[idx]
        self.sort(sortby)
        # find new index of the record
        if uuid:
            g = (i for i, x in enumerate(self.records) if x == uuid)  # generator
            idx2 = next(g, 0)
        else:
            idx2 = 0
        self.win.idx = idx2
        self.refresh_all()

    def create_windows(self):
        '''
        <project> v...file...time...
        Search: ...
        ... header ...
        records ... | record |
            2/3        1/3
        ---------------------
        status ...
        '''
        maxy, maxx = self.screen_size
        self.win_header = self.screen.derwin(1, maxx, 0, 0)

        rows, cols = (maxy - 6, maxx)
        cols2 = min(cols // 3, 35)
        cols1 = cols - cols2
        if no_win2 := cols1 < sum(self.row_string.widths[:3]):
            cols1 = cols

        prompt = self.prompt_search = ' Search: '
        len_ = len(prompt)
        self.win_search = self.screen.derwin(1, maxx - len_, 1, len_)

        win = self.screen.derwin(rows, cols1 - 3, 4, 2)
        self.win = List3(win, self, height=2, current_color=curses.color_pair(1))

        if no_win2:
            self.win2 = None
        else:
            self.win2 = self.screen.derwin(maxy - 3, cols2, 2, cols1)

        # status
        self.win3 = self.screen.derwin(1, maxx, maxy - 1, 0)

    def refresh_win_deps(self):
        if not self.win2:
            return
        rows, cols = self.win2.getmaxyx()
        rows -= 2  # -borders
        cols -= 2  # -borders
        win = self.win2.derwin(rows, cols, 1, 1)
        win.erase()
        idx = self.win.idx
        if idx < len(self.records):
            uuid = self.records[idx]
            r = self.db.get_by_uuid(uuid)
            record2win(r, win)
        self.win2.refresh()

    def del_record(self, i: int):
        if not (uuid := self.get_record(i)):
            return
        if ask_delete(self.screen, color=curses.color_pair(2)):
            if self.db.mark_del(uuid, True):
                del self.records[i]
            else:
                self.status(f'error: {self.db.error}')
        self.win.refresh()

    def get_record(self, i: int) -> str | None:
        len_ = len(self.records)
        if i >= len_:
            return None
        return self.records[i]

    def get_record_str(self, i: int) -> Generator[str]:
        if (uuid := self.get_record(i)) and (r := self.db.get_by_uuid(uuid)):
            yield self.row_string.value(r.title, int2time(r.last_mod), int2time(r.created), r.url)
            yield self.row_string2.value('', r.tags)

    def records_len(self) -> int:
        return len(self.records)

    def filter_record(self, record: Record):
        return self.filter.found(record.title, record.tags, record.url)

    def create_header(self):
        headers = []
        for key2 in HEADER_KEYS:
            title = HEADER[key2]
            match is_sorted(key2, self.sortedby):
                case SORTED.ASC:
                    headers.append(f'{title}({SORT_DOWN}):')
                case SORTED.DESC:
                    headers.append(f'{title}({SORT_UP}):')
                case SORTED.NO:
                    headers.append(f'{title}:')
        return self.row_string.value(*headers)

    def show_header(self):
        s = APP_HEADER
        if self.show_deleted:
            s += ' - deleted!'
        self.win_header.erase()
        win_addstr(self.win_header, 0, 1, s)
        self.win_header.refresh()

    def refresh_all(self):
        self.screen.clear()

        self.show_header()

        win_addstr(self.screen, 1, 0, self.prompt_search)
        self.screen.refresh()

        self.win_search.erase()
        win_addstr(self.win_search, 0, 0, self.filter.filter_string)
        self.win_search.refresh()

        maxy, maxx = self.screen_size
        win = self.screen.derwin(maxy - 3, maxx, 2, 0)
        win.erase()
        win_addstr(win, 1, 2, self.create_header())
        win.box()
        win.refresh()

        self.win.refresh()

        if self.win2:
            self.win2.erase()
            self.win2.border(0, 0, 0, 0, curses.ACS_TTEE, 0, curses.ACS_BTEE, 0)
            self.win2.refresh()

        self.refresh_win_deps()

    def run(self):
        self.refresh_all()
        self.input_loop()

    def handle_alt_key(self, ch: int):
        if (ch2 := chr(ch)) in SORT:
            self.sort2(SORT(ch2))

    def status(self, s: str):
        win = self.win3
        win.erase()
        win_addstr(win, 0, 1, s)
        win.refresh()

    def search(self):
        ok, s = input_search(self, self.prompt_search.lstrip())
        if ok:
            self.filter.set(s)
            win_addstr(self.win_search, 0, 0, self.filter.filter_string)
            self.sort2(self.sortedby)

    def run_url(self):
        if (uuid := self.get_record(self.win.idx)) and (r := self.db.get_by_uuid(uuid)) and r.url:
            pass
        else:
            return
        try:
            if shutil.which("xdg-open"):
                subprocess.run(['xdg-open', r.url], check=False)
            else:
                webbrowser.open(r.url)
        except ImportError:
            self.status(f'Could not load python module "webbrowser" for {r.url=}')

    def show_url(self):
        if (uuid := self.get_record(self.win.idx)) and (r := self.db.get_by_uuid(uuid)):
            pass
        else:
            return
        if r.url:
            if shutil.which("qrencode"):
                with escape2terminal(self):
                    print(f'URL: {r.url}')
                    subprocess.run(['qrencode', '-t', 'ansiutf8', '-o', '-', r.url], check=False)
                    input('Press Enter to continue...')
            else:
                self.status('qrencode not found!')
        else:
            self.status('URL is empty')

    def url2clipboard(self):
        if (uuid := self.get_record(self.win.idx)) and (r := self.db.get_by_uuid(uuid)):
            pass
        else:
            return
        if r.url:
            str2clipboard(r.url)
            self.status('URL copied to clipboard')
        else:
            self.status('URL is empty')

    def title2clipboard(self):
        if (uuid := self.get_record(self.win.idx)) and (r := self.db.get_by_uuid(uuid)):
            pass
        else:
            return
        if r.title:
            str2clipboard(r.title)
            self.status('Title copied to clipboard')
        else:
            self.status('Title is empty')

    def input_loop(self):  # pylint: disable=too-many-branches,too-many-statements
        for char_ord in self.getch():
            char = chr(char_ord)

            if char_ord == curses.KEY_DC:  # delete
                self.del_record(self.win.idx)
            elif char_ord == curses.KEY_IC:  # insert
                self.insert_record(self.win.idx)
            elif self.win.handle_input(char_ord):
                pass
            elif char == 'e':
                self.edit_record(self.win.idx)  # not using curses
            elif char == 's':
                self.filter.set()
                self.search()
            elif char == 'L':
                self.run_url()
            elif char == 'I':
                self.import_html()
            elif char == 'D':
                self.show_deleted = not self.show_deleted
                self.show_header()
                self.sort2(self.sortedby)
            elif char == 'U':
                self.show_url()
            elif char.upper() == 'H':  # Print help screen
                win_help(self.win.win, HELP)
                self.refresh_all()
            elif char_ord == 12:  # ^L
                self.url2clipboard()
            elif char_ord == 20:  # ^T
                self.title2clipboard()
            else:
                name = curses.keyname(char_ord).decode('utf-8')
                self.status(f'{char_ord=}, {name=}')

    def edit_record(self, i: int):
        if (uuid := self.get_record(i)) and (r := self.db.get_by_uuid(uuid)):
            pass
        else:
            return
        res = EDIT.NONE
        with escape2terminal(self):
            res = self.db.edit_record(r)
        match res:
            case EDIT.NONE:
                pass
            case EDIT.OK1:
                self.win.refresh()
            case EDIT.OK2:
                self.sort2(self.sortedby)
            case _:
                self.status(f'error: {self.db.error}')

    def insert_record(self, i: int):
        r = Record.create()
        res = EDIT.NONE
        with escape2terminal(self):
            res = self.db.insert_record(r)
        match res:
            case EDIT.NONE:
                pass
            case EDIT.OK1:
                self.records.insert(i, r.uuid)
                self.win.refresh()
            case EDIT.OK2:
                self.records.insert(i, r.uuid)
                self.sort2(self.sortedby)
            case _:
                self.status(f'error: {self.db.error}')

    def import_html(self):
        with escape2terminal(self):
            res = import_html(self.db)
        self.sort(self.sortedby)
        self.win.refresh()
        if res.ok:
            self.status(f'added: {res.added}, skipped: {res.skipped}')
        else:
            self.status(f'error: {res.line}: {res.error}')


def record2win(r: Record | None, win):
    if not r:
        win.erase()
        return
    rows, cols = win.getmaxyx()
    row = -1
    for line in record2str(r).splitlines():
        for s in chunkstring(line, cols):
            row += 1
            if not row < rows:
                return
            win_addstr(win, row, 0, s)


def main2(db, screen):
    app = Main(db, screen)
    app.run()


def main():
    try:
        fpath = input_file('sqlite file: ')
        if not os.path.exists(fpath):
            print(f'New sqlite file: {fpath}')
    except KeyboardInterrupt:
        return
    with sqlite_db(fpath) as db:
        main2_ = partial(main2, db)
        curses.wrapper(main2_)


if __name__ == '__main__':
    main()
