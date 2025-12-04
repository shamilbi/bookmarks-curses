import curses
from typing import Generator, Protocol

from . import win_addstr


class ListProto3(Protocol):
    def get_record_str(self, i: int) -> Generator[str]:
        'yields <height> lines'

    def records_len(self) -> int:
        pass

    def refresh_win_deps(self):
        pass


class List3:
    'List + every record projects to <height> window lines'

    def __init__(
        self,
        win: curses.window,
        proto: ListProto3,
        height: int = 1,
        current_color: int = curses.A_BOLD,
    ):
        self.win = win
        self.height = height
        self.proto = proto
        self.current_color = current_color

        self.win.keypad(True)

        self.cur = 0  # cursor y, = 0..(maxy // height), real cursor = cur * height
        self.idx = 0  # source index

    def addstr(self, i: int, g: Generator[str], attr: int = 0):
        i2 = i * self.height
        j = -1
        for j, s in enumerate(g):
            if j >= self.height:
                break
            if not j:
                # first line
                win_addstr(self.win, i2 + j, 0, s, attr=attr | curses.A_BOLD)
            else:
                # rest of lines
                win_addstr(self.win, i2 + j, 0, s, attr=attr | curses.A_DIM)
        if j < self.height - 1:
            # print rest lines
            from_ = j + 1
            for j in range(from_, self.height):
                win_addstr(self.win, i2 + j, 0, '', attr=attr)

    def refresh(self):
        self.win.erase()
        len_ = self.proto.records_len()
        if len_:
            rows, _ = self.win.getmaxyx()
            rows //= self.height
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
                    self.addstr(i, s, attr=self.current_color)
                else:
                    self.addstr(i, s)
            self.win.move(self.cur * self.height, 0)
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
        rows //= self.height
        self.cur = min(rows - 1, len_ - 1)
        self.idx = len_ - 1
        self.refresh()

    def scroll_down(self):
        len_ = self.proto.records_len()
        if not len_ or not self.idx + 1 < len_:
            return
        rows, _ = self.win.getmaxyx()
        rows //= self.height
        prev_s = self.proto.get_record_str(self.idx)
        next_s = self.proto.get_record_str(self.idx + 1)
        self.addstr(self.cur, prev_s)
        if self.cur + 1 < rows:
            self.cur += 1
        else:
            self.win.move(0, 0)
            self.win.deleteln()
            self.win.deleteln()
            self.cur = rows - 1
        self.addstr(self.cur, next_s, attr=self.current_color)
        self.idx += 1
        self.win.refresh()
        self.proto.refresh_win_deps()

    def scroll_up(self):
        len_ = self.proto.records_len()
        if not len_ or self.idx - 1 < 0:
            return
        prev_s = self.proto.get_record_str(self.idx)
        next_s = self.proto.get_record_str(self.idx - 1)
        self.addstr(self.cur, prev_s)
        if self.cur > 0:
            self.cur -= 1
        else:
            self.win.move(0, 0)
            self.win.insdelln(self.height)
        self.addstr(self.cur, next_s, attr=self.current_color)
        self.idx -= 1
        self.win.refresh()
        self.proto.refresh_win_deps()

    def scroll_page_down(self):
        len_ = self.proto.records_len()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        rows //= self.height
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
        rows //= self.height
        idx = self.idx - rows
        if idx >= 0:
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
