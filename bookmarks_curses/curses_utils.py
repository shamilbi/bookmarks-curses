import curses
import curses.ascii
import os
import sys
from signal import SIGINT, SIGTERM, SIGWINCH, signal
from typing import Generator, Protocol


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


class ListProto(Protocol):
    def get_record_str(self, i: int) -> str:
        pass

    def records_len(self) -> int:
        pass

    def refresh_win_deps(self):
        pass


class List:
    '''
    A projection of an array of records r0...rX to a window lines of string s0...sY
    where si = get_record_str(j) = rj -> str, s(i+1) = get_record_str(j+1), j < records_len()
    and changing cursor (i) leads to call refresh_win_deps()
    '''

    def __init__(
        self,
        win: curses.window,
        proto: ListProto,
        current_color: int = curses.A_BOLD,
    ):
        self.win = win
        self.proto = proto
        self.current_color = current_color

        self.win.keypad(True)

        self.cur = 0  # cursor y
        self.idx = 0  # source index

    def refresh(self):
        self.win.erase()
        len_ = self.proto.records_len()
        if len_:
            rows, _ = self.win.getmaxyx()
            if not self.idx < len_:  # deleted
                self.idx = len_ - 1
            if (rows - self.cur) > (di := len_ - self.idx):
                # gap at bottom
                self.cur = rows - di
            self.cur = min(self.cur, self.idx)
            for i in range(rows):
                idx = self.idx - self.cur + i
                if not idx < len_:
                    break
                s = self.proto.get_record_str(idx)
                if i == self.cur:
                    win_addstr(self.win, i, 0, s, attr=self.current_color)
                else:
                    win_addstr(self.win, i, 0, s)
            self.win.move(self.cur, 0)
        self.win.refresh()
        self.proto.refresh_win_deps()

    def scroll_top(self):
        self.idx = self.cur = 0
        self.refresh()

    def scroll_bottom(self):
        len_ = self.proto.records_len()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        self.cur = min(rows - 1, len_ - 1)
        self.idx = len_ - 1
        self.refresh()

    def scroll_down(self):
        len_ = self.proto.records_len()
        if not len_ or not self.idx + 1 < len_:
            return
        rows, _ = self.win.getmaxyx()
        prev_s = self.proto.get_record_str(self.idx)
        next_s = self.proto.get_record_str(self.idx + 1)
        win_addstr(self.win, self.cur, 0, prev_s)
        if self.cur + 1 < rows:
            self.cur += 1
        else:
            self.win.move(0, 0)
            self.win.deleteln()
            self.cur = rows - 1
        win_addstr(self.win, self.cur, 0, next_s, attr=self.current_color)
        self.idx += 1
        self.win.refresh()
        self.proto.refresh_win_deps()

    def scroll_up(self):
        len_ = self.proto.records_len()
        if not len_ or self.idx - 1 < 0:
            return
        prev_s = self.proto.get_record_str(self.idx)
        next_s = self.proto.get_record_str(self.idx - 1)
        win_addstr(self.win, self.cur, 0, prev_s)
        if self.cur > 0:
            self.cur -= 1
        else:
            self.win.move(0, 0)
            self.win.insdelln(1)
        win_addstr(self.win, self.cur, 0, next_s, attr=self.current_color)
        self.idx -= 1
        self.win.refresh()
        self.proto.refresh_win_deps()

    def scroll_page_down(self):
        len_ = self.proto.records_len()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        idx = self.idx + rows
        if idx < len_:
            self.idx = idx
            self.refresh()
        else:
            idx = len_ - 1
            delta = idx - self.idx
            if not delta:
                self.scroll_bottom()
            elif self.cur + delta < rows:
                self.cur += delta
                self.idx = idx
                self.refresh()
            else:
                self.scroll_bottom()

    def scroll_page_up(self):
        len_ = self.proto.records_len()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        idx = self.idx - rows
        if not idx < 0:
            self.idx = idx
            self.refresh()
        else:
            self.scroll_top()

    def handle_input(self, ch: int) -> bool:
        char = chr(ch)
        if char.upper() == 'J' or ch == curses.KEY_DOWN:  # Down or J
            self.scroll_down()
        elif char.upper() == 'K' or ch == curses.KEY_UP:  # Up or K
            self.scroll_up()
        elif char == 'g' or ch == curses.KEY_HOME:  # Move to top
            self.scroll_top()
        elif char == 'G' or ch == curses.KEY_END:  # Move to last item
            self.scroll_bottom()
        elif ch == curses.KEY_NPAGE:  # Page down
            self.scroll_page_down()
        elif ch == curses.KEY_PPAGE:  # Page up
            self.scroll_page_up()
        else:
            return False
        return True


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


def input_search(app: App, prompt: str) -> tuple[bool, str]:  # ok, search str
    curses.endwin()
    old = signal(SIGINT, app.orig_sigint)
    try:
        return (True, input(prompt))
    except KeyboardInterrupt:
        pass
    finally:
        # clear terminal for privacy
        os.system('cls' if os.name == 'nt' else 'clear')
        app.screen.refresh()
        signal(SIGINT, old)
    return (False, '')
