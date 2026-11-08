import curses
import curses.ascii
import os
import shutil
import subprocess
import webbrowser
from collections.abc import Generator
from functools import partial

from curses_utils2.app2 import AppProto, AppSwitch, AppSwitchProto
from curses_utils2.file_utils import input_file
from curses_utils2.list3_v2 import List3v2, ListProto3
from curses_utils2.record import record2str
from curses_utils2.text import win_help
from curses_utils2.utils import RowString, chunkstring, screen_size, start_curses_app
from curses_utils2.win import ask_delete, win_addstr
from curses_utils2.winbox import WinBox, WinProto

from . import __project_name__, __version__
from .db import (
    EDIT,
    SORT,
    SORTED,
    Record,
    create_tables,
    is_sorted,
)
from .import_diigo import import_html
from .sqlite_utils import DbProto, sqlite_db
from .utils import (
    FilterString,
    int2time,
    str2clipboard,
)

APP_HEADER = f'{__project_name__} v{__version__} (F1 - Help)'

HELP = [
    ("F1", "This help screen"),
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
    ("Ctrl-G", "Copy Tags to clipboard"),
]

HEADER_KEYS = ('t', 'm', 'c', 'u')
HEADER: dict[str, str] = dict(zip(HEADER_KEYS, ('Title', 'ModTime', 'Created', 'URL')))

SORT_UP = '\u2191'
SORT_DOWN = '\u2193'


class Win2(WinProto):
    def __init__(self, app: "App"):
        self.app = app
        self.win: curses.window | None = None

        self.r0 = Record()

    def set_win(self, win: curses.window | None):
        self.win = win

    def refresh(self):
        if not self.win:
            return
        app = self.app
        win = self.win

        win.erase()
        if app.win.win:
            _, r = app.get_uuid_r()
            if r:
                record2win(r, win)
        win.refresh()


class List1(ListProto3):
    def __init__(self, app: "App"):
        self.app = app
        self.r0 = Record()

    def get_record_str(self, i: int) -> Generator[str]:
        'yields <height> lines'
        app = self.app
        if (uuid := app.get_record(i)) and (r := self.r0.get_by_uuid(app.db, uuid)):
            yield app.row_string.value(
                r.title,
                int2time(r.last_mod, '%Y-%m-%d'),
                int2time(r.created, '%Y-%m-%d'),
                r.url,
            )
            yield app.row_string2.value('', r.tags)

    def records_len(self) -> int:
        return len(self.app.records)

    def refresh_win_deps(self):
        self.app.win2box.refresh()


class App(AppProto):
    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    # pylint: disable=attribute-defined-outside-init
    def __init__(self, db: DbProto, parent: AppSwitchProto):
        self.db = db
        self.r0 = Record()

        self.parent = parent
        self.screen = self.parent.screen

        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)

        self.records: list[str] = []  # uuid
        self.filter = FilterString()
        self.show_deleted = False
        self.sortedby = SORT.LAST_MOD

        # title, last_mod, created, tags
        self.row_string = RowString(70, 10, 10, 0)  # title, last_mod, created, url
        self.row_string2 = RowString(4, 70 - 4)  # indent, tags

        self.win = List3v2(
            List1(self),
            height=2,
            current_color=curses.color_pair(1),
        )
        self.listbox = WinBox(self.win, offy=1)

        self.win2box = WinBox(Win2(self))

    def sigwinch_handler(self, *_):
        self.create_windows()
        self.refresh_all()

    def run(self):
        self.sort(self.sortedby)
        self.create_windows()
        self.refresh_all()

    def sort(self, sortby: SORT):
        self.sortedby = sortby
        self.records = [r.uuid for r in self.r0.sort(self.db, sortby, self.show_deleted) if self.filter_record(r)]

    def sort2(self, sortby: SORT):
        idx = self.win.idx
        uuid = None
        if idx < len(self.records):
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
        maxy, maxx = screen_size()
        self.win_header = self.screen.derwin(1, maxx, 0, 0)

        cols = maxx
        cols2 = 35
        cols1 = cols - cols2
        min_width1 = sum(self.row_string.widths[:3]) + 3 + 2  # 3 spaces + 2 border
        if no_win2 := (cols - cols2) < min_width1:
            cols1 = cols

        prompt = self.prompt_search = ' Search: '
        len_ = len(prompt)
        self.win_search = self.screen.derwin(1, maxx - len_, 1, len_)

        win = self.screen.derwin(maxy - 3, cols1, 2, 0)
        self.listbox.set_win(win)

        if no_win2:
            win2 = None
        else:
            win2 = self.screen.derwin(maxy - 3, cols2, 2, cols1)
        self.win2box.set_win(win2)

        # status
        self.win3 = self.screen.derwin(1, maxx, maxy - 1, 0)

    def del_record(self, i: int):
        if not (uuid := self.get_record(i)):
            return
        if ask_delete(self.screen, color=curses.color_pair(2)):
            if self.r0.mark_del(self.db, uuid):
                del self.records[i]
            else:
                self.status(f'error: {self.db.error}')
        self.win.refresh()

    def get_record(self, i: int) -> str | None:
        len_ = len(self.records)
        if i >= len_:
            return None
        return self.records[i]

    def filter_record(self, record: Record):
        return self.filter.found(record.title, record.url, tags=record.tags)

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
        self.screen.erase()
        self.screen.refresh()

        self.show_header()

        win_addstr(self.screen, 1, 0, self.prompt_search)

        self.win_search.erase()
        win_addstr(self.win_search, 0, 0, self.filter.filter_string)
        self.win_search.refresh()

        self.listbox.refresh(self.create_header())

        self.screen.refresh()

    def handle_alt_key(self, ch: int):
        if (ch2 := chr(ch)) in SORT:
            self.sort2(SORT(ch2))

    def status(self, s: str):
        win = self.win3
        win.erase()
        win_addstr(win, 0, 1, s)
        win.refresh()

    def search(self):
        ok, s = self.parent.input_search(self.prompt_search.lstrip())
        if ok:
            self.filter.set(s)
            win_addstr(self.win_search, 0, 0, self.filter.filter_string)
            self.sort2(self.sortedby)

    def get_uuid_r(self) -> tuple[str | None, Record | None]:
        'current uuid, Record'
        uuid = self.get_record(self.win.idx)
        if not uuid:
            return None, None
        r = self.r0.get_by_uuid(self.db, uuid)
        if not r:
            return uuid, None
        return uuid, r

    def run_url(self):
        uuid, r = self.get_uuid_r()
        if uuid and r and r.url:
            pass
        else:
            return
        try:
            if shutil.which("xdg-open"):
                subprocess.run(['xdg-open', r.url], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(r.url)
        except ImportError:
            self.status(f'Could not load python module "webbrowser" for {r.url=}')

    def show_url(self):
        uuid, r = self.get_uuid_r()
        if uuid and r:
            pass
        else:
            return
        if r.url:
            if shutil.which("qrencode"):
                with self.parent.escape2terminal():
                    print(f'URL: {r.url}')
                    subprocess.run(['qrencode', '-t', 'ansiutf8', '-o', '-', r.url], check=False)
                    input('Press Enter to continue...')
            else:
                self.status('qrencode not found!')
        else:
            self.status('URL is empty')

    def url2clipboard(self):
        uuid, r = self.get_uuid_r()
        if uuid and r:
            pass
        else:
            return
        if r.url:
            str2clipboard(r.url)
            self.status('URL copied to clipboard')
        else:
            self.status('URL is empty')

    def title2clipboard(self):
        uuid, r = self.get_uuid_r()
        if uuid and r:
            pass
        else:
            return
        if r.title:
            str2clipboard(r.title)
            self.status('Title copied to clipboard')
        else:
            self.status('Title is empty')

    def tags2clipboard(self):
        uuid, r = self.get_uuid_r()
        if uuid and r:
            pass
        else:
            return
        if r.tags:
            str2clipboard(r.tags)
            self.status('Tags copied to clipboard')
        else:
            self.status('Tags is empty')

    # pylint: disable=too-many-branches,too-many-statements,useless-return
    def handle_key(self, ch: int) -> str | None:  # switch to another app?
        char = chr(ch)

        if ch == curses.KEY_DC:  # delete
            self.del_record(self.win.idx)
        elif ch == curses.KEY_IC:  # insert
            self.insert_record(self.win.idx)
        elif self.win.handle_input(ch):
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
        elif ch == curses.KEY_F1:
            win = self.win.win
            if win:
                win_help(win, HELP)
                self.refresh_all()
        elif ch == 12:  # ^L
            self.url2clipboard()
        elif ch == 20:  # ^T
            self.title2clipboard()
        elif ch == 7:  # ^G
            self.tags2clipboard()
        else:
            name = curses.keyname(ch).decode('utf-8')
            self.status(f'{ch=}, {name=}')
        return None

    def edit_record(self, i: int):
        if (uuid := self.get_record(i)) and (r := self.r0.get_by_uuid(self.db, uuid)):
            pass
        else:
            return
        res = EDIT.NONE
        with self.parent.escape2terminal():
            res = r.edit_record(self.db)
        match res:
            case EDIT.NONE:
                pass
            case EDIT.OK:
                self.sort2(self.sortedby)
            case _:
                self.status(f'error: {self.db.error}')

    def insert_record(self, i: int):
        r = Record()
        res = EDIT.NONE
        with self.parent.escape2terminal():
            res = r.insert_record(self.db)
        match res:
            case EDIT.NONE:
                pass
            case EDIT.OK:
                self.records.insert(i, r.uuid)
                self.sort2(self.sortedby)
            case _:
                self.status(f'error: {self.db.error}')

    def import_html(self):
        with self.parent.escape2terminal():
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

    # time
    for i, prefix in [(r.created, 'Created'), (r.last_mod, 'Modified')]:
        row += 1
        s = int2time(i, '%Y-%m-%d %H:%M:%S')
        win_addstr(win, row, 0, f'{prefix}: {s}')

    # separator
    row += 1
    win_addstr(win, row, 0, '')

    # record
    for line in record2str(r).splitlines():
        for s in chunkstring(line, cols):
            row += 1
            if not row < rows:
                return
            win_addstr(win, row, 0, s)


class Main(AppSwitch):
    def __init__(self, db, screen):
        super().__init__(screen)
        self.app = App(db, self)
        self.apps = {'b': self.app}

    def get_info(self, about: str) -> dict:
        return {}


def main2(db, screen):
    app = Main(db, screen)
    app.run()


def main():
    print(f'{__project_name__} v{__version__}')
    try:
        fpath = input_file('sqlite file: ')
        if not os.path.exists(fpath):
            print(f'New sqlite file: {fpath}')
    except KeyboardInterrupt:
        return
    with sqlite_db(fpath) as db:
        create_tables(db)
        main2_ = partial(main2, db)
        start_curses_app(main2_, __project_name__, __version__)


if __name__ == '__main__':
    main()
