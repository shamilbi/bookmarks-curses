import curses
import curses.ascii

from .win import get_alt_key, win_addstr, win_center


class Text:

    def __init__(self, win: curses.window, text: list[str]):
        self.win = win
        self.text = text

        self.height = len(text)
        self.width = max(len(i) for i in text) if text else 0
        self.y = self.x = 0  # left top point in text
        # y < height - win.maxy
        # x < width - win.maxx

        self.win.keypad(True)

    def refresh(self):
        self.win.erase()
        len_ = self.height
        if len_:
            rows, _ = self.win.getmaxyx()
            if not self.y <= len_ - rows:
                self.y = max(len_ - rows, 0)
            for i in range(rows):
                idx = self.y + i
                if not idx < len_:
                    break
                s = self.text[idx][self.x :]
                win_addstr(self.win, i, 0, s)
        self.win.refresh()

    def scroll_top(self):
        self.y = 0
        self.refresh()

    def scroll_bottom(self):
        rows, _ = self.win.getmaxyx()
        self.y = max(self.height - rows, 0)
        self.refresh()

    def scroll_down(self):
        rows, _ = self.win.getmaxyx()
        if self.y + 1 <= self.height - rows:
            self.win.move(0, 0)
            self.win.deleteln()
            s = self.text[self.y + rows][self.x :]
            win_addstr(self.win, rows - 1, 0, s)
            self.y += 1
        self.win.refresh()

    def scroll_up(self):
        if self.y > 0:
            self.win.move(0, 0)
            self.win.insdelln(1)
            s = self.text[self.y - 1][self.x :]
            win_addstr(self.win, 0, 0, s)
            self.y -= 1
        self.win.refresh()

    def scroll_page_down(self):
        rows, _ = self.win.getmaxyx()
        idx = self.y + rows
        if idx < self.height:
            self.y = idx
            self.refresh()
        else:
            self.scroll_bottom()

    def scroll_page_up(self):
        rows, _ = self.win.getmaxyx()
        idx = self.y - rows
        if not idx < 0:
            self.y = idx
            self.refresh()
        else:
            self.scroll_top()

    def scroll_right(self):
        _, cols = self.win.getmaxyx()
        if self.x + 1 <= self.width - cols:
            self.x += 1
        self.refresh()

    def scroll_left(self):
        if self.x > 0:
            self.x -= 1
        self.refresh()

    def handle_input(self, ch: int):
        char = chr(ch)
        if char.upper() == 'J' or ch == curses.KEY_DOWN:  # Down or J
            self.scroll_down()
        elif char.upper() == 'K' or ch == curses.KEY_UP:  # Up or K
            self.scroll_up()
        elif char == 'g' or ch == curses.KEY_HOME:  # Home or g
            self.scroll_top()
        elif char == 'G' or ch == curses.KEY_END:  # End or G
            self.scroll_bottom()
        elif ch == curses.KEY_NPAGE:  # Page down
            self.scroll_page_down()
        elif ch == curses.KEY_PPAGE:  # Page up
            self.scroll_page_up()
        elif char.upper() == 'L' or ch == curses.KEY_RIGHT:  # Right or l
            self.scroll_right()
        elif char.upper() == 'H' or ch == curses.KEY_LEFT:  # Left or h
            self.scroll_left()

    def input_loop(self):
        self.refresh()
        while True:
            try:
                ch = self.win.getch()

                if ch == -1:
                    # SIGWINCH interrupt
                    # t = self.win.getmaxyx()  # doesn't work
                    continue

                if ch == curses.ascii.ESC:  # Esc
                    get_alt_key(self.win)  # skip
                elif ch == curses.KEY_RESIZE:
                    # doesn't work
                    # t = self.win.getmaxyx()
                    pass
                else:
                    char = chr(ch)
                    if char.upper() == 'Q' or ch == curses.KEY_F1:
                        break
                    self.handle_input(ch)
            except curses.error:
                pass


def win_help(screen: curses.window, help_: list[tuple[str, str]]):  # pylint: disable=too-many-locals
    '''
    help_ = [
        (key1, help1),
        (key2, help2),
        ...
    ]
    '''
    header = "Help (q,F1: Exit)"

    lmax = max(len(i[0]) for i in help_)  # (lmax) - help

    # def iter_help():
    #     for i, j in help_:
    #         yield f'{i:<{lmax}} - {j}'  # keys - help
    text = [f'{i:<{lmax}} - {j}' for i, j in help_]  # key - help

    rows = len(help_)
    rows2 = rows + 2  # border=2
    # cols = max(len(header), max(len(i) for i in iter_help()), len(footer))
    cols = max(len(header), max(len(i) for i in text))
    cols2 = cols + 2  # border=2

    win = win_center(screen, rows2, cols2, header)
    rows3, cols3 = win.getmaxyx()
    win.refresh()

    win2 = win.derwin(rows3 - 2, cols3 - 2, 1, 1)
    text2 = Text(win2, text)

    # row = 0
    # col = 1
    # for s in iter_help():
    #     row += 1
    #     win_addstr(win, row, col, s, border=1)
    # row += 1
    # win_addstr(win, row, col, footer, border=1)

    # # Wait for any key press
    # win.getch()

    text2.input_loop()

    # https://stackoverflow.com/questions/2575409/how-do-i-delete-a-curse-window-in-python-and-restore-background-window
    win2.erase()
    del win2
    win.erase()
    del win
    screen.touchwin()
