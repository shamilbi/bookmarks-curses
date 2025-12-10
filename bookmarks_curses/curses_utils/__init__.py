import curses
import curses.ascii
import os
import sys
from contextlib import contextmanager
from signal import SIGINT, SIGTERM, SIGWINCH, signal
from typing import Generator


def win_addstr(
    win: curses.window, row: int, col: int, s: str, attr: int = 0, border: int = 0, align: int = -1
):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    'align: -1 (left), 0(center), 1(right)'
    try:
        _, cols = win.getmaxyx()
        cols2 = cols - col - border
        s = s[:cols2]
        if align == 0:
            s = f'{s:^{cols2}}'
        elif align > 0:
            s = f'{s:>{cols2}}'
        win.addstr(row, col, s, attr)
    except curses.error:
        # https://docs.python.org/3/library/curses.html#curses.window.addstr
        # Attempting to write to the lower right corner of a window, subwindow, or pad
        # will cause an exception to be raised after the string is printed.
        pass


def win_center(screen: curses.window, rows: int, cols: int, header: str, color: int = 0) -> curses.window:
    max_rows, max_cols = screen.getmaxyx()
    rows = min(rows, max_rows)
    cols = min(cols, max_cols)
    y = (max_rows - rows) // 2
    x = (max_cols - cols) // 2

    win = screen.derwin(rows, cols, y, x)
    win.keypad(True)
    win.erase()
    if color:
        win.attrset(color)
    win.box()

    header = header[:cols]
    x = (cols - len(header)) // 2
    win_addstr(win, 0, x, header)

    return win


def ask_delete(screen: curses.window, color: int = 0) -> bool:
    header = 'Delete current record'
    win = win_center(screen, 5, 30, header, color=color)

    win_addstr(win, 1, 1, 'Are you sure?', border=1, align=0)
    win_addstr(win, 3, 1, 'Press Y to delete ...', border=1, align=0)

    try:
        ch = win.getch()
        if ch == ord('Y'):
            return True
        return False
    except curses.error:
        return False
    finally:
        # https://stackoverflow.com/questions/2575409/how-do-i-delete-a-curse-window-in-python-and-restore-background-window
        win.erase()
        del win
        screen.touchwin()


def win_help(screen, help_: list[tuple[str, str]]):  # pylint: disable=too-many-locals
    '''
    help_ = [
        (key1, help1),
        (key2, help2),
        ...
    ]
    '''
    header = "Help information:"
    footer = "Press any key to continue..."

    lmax = max(len(i[0]) for i in help_)  # (lmax) - help

    def iter_help():
        for i, j in help_:
            yield f'{i:<{lmax}} - {j}'  # keys - help

    rows = len(help_) + 1  # footer=1
    rows2 = rows + 2  # border=2
    cols = max(len(header), max(len(i) for i in iter_help()), len(footer))
    cols2 = cols + 2  # border=2

    win = win_center(screen, rows2, cols2, header)
    rows2, cols2 = win.getmaxyx()

    row = 0
    col = 1
    for s in iter_help():
        row += 1
        win_addstr(win, row, col, s, border=1)
    row += 1
    win_addstr(win, row, col, footer, border=1)

    # Wait for any key press
    win.getch()

    # https://stackoverflow.com/questions/2575409/how-do-i-delete-a-curse-window-in-python-and-restore-background-window
    win.erase()
    del win
    screen.touchwin()


class App:
    def __init__(self, screen):
        self.screen = screen

        self.orig_sigint = signal(SIGINT, self.shutdown)
        signal(SIGTERM, self.shutdown)
        signal(SIGWINCH, self.sigwinch_handler)

        self.screen.keypad(1)
        curses.curs_set(0)
        curses.noecho()
        curses.start_color()

        self.screen_size = (curses.LINES, curses.COLS)  # pylint: disable=no-member

    def sigwinch_handler(self, *_):
        maxx, maxy = os.get_terminal_size()
        self.screen_size = (maxy, maxx)
        self.create_windows()
        self.refresh_all()

    def shutdown(self, *_):
        if curses.isendwin():
            # return to curses
            self.screen.refresh()
        sys.exit(0)

    def create_windows(self):
        pass

    def refresh_all(self):
        pass

    def handle_alt_key(self, ch: int):
        pass

    def _handle_alt_key(self):
        # https://stackoverflow.com/a/22362849
        ch = -1
        try:
            self.screen.nodelay(True)
            ch = self.screen.getch()  # get the key pressed after ALT
        finally:
            self.screen.nodelay(False)
        if ch == -1:
            self.shutdown()
        self.handle_alt_key(ch)

    def getch(self) -> Generator[int, None, None]:
        while True:
            try:
                ch = self.screen.getch()

                if ch == -1:
                    # SIGWINCH interrupt
                    # t = self.screen.getmaxyx()  # doesn't work
                    continue

                if ch == curses.ascii.ESC:  # Esc
                    self._handle_alt_key()
                elif ch == curses.KEY_RESIZE:
                    # doesn't work
                    # t = self.screen.getmaxyx()
                    pass
                else:
                    char = chr(ch)
                    if char.upper() == 'Q':
                        self.shutdown()
                    else:
                        yield ch
            except curses.error:
                pass


@contextmanager
def escape2terminal(app: App):
    def _clear():
        # clear terminal for privacy
        os.system('cls' if os.name == 'nt' else 'clear')

    curses.endwin()
    old = signal(SIGINT, app.orig_sigint)
    try:
        _clear()
        yield
    except KeyboardInterrupt:
        pass
    finally:
        _clear()
        app.screen.refresh()
        signal(SIGINT, old)


def input_search(app: App, prompt: str) -> tuple[bool, str]:  # ok, search str
    with escape2terminal(app):
        try:
            return (True, input(prompt))
        except KeyboardInterrupt:
            pass
    return (False, '')
