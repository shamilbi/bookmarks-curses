import curses
import curses.ascii
import sys


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


def set_terminal_title(title: str):
    # https://stackoverflow.com/questions/23388262/is-there-a-way-to-change-the-terminal-title-with-curses
    sys.stdout.write(f"\x1b]2;{title}\x07")
    sys.stdout.flush()


def get_alt_key(screen: curses.window) -> int:
    # https://stackoverflow.com/a/22362849
    try:
        screen.nodelay(True)
        return screen.getch()  # get the key pressed after ALT
    finally:
        screen.nodelay(False)
