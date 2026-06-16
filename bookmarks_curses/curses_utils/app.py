import curses
import curses.ascii
import os
import sys
from collections.abc import Callable
from contextlib import contextmanager
from signal import SIGINT, SIGTERM, SIGWINCH, signal
from typing import Generator

from .win import get_alt_key, set_terminal_title


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
        ch = get_alt_key(self.screen)
        if ch == -1:
            # https://docs.python.org/3/library/curses.html#curses.window.getch
            # In no-delay mode, return -1 if there is no input, otherwise wait until a key is pressed
            return
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


def start_curses_app(
    main: Callable[[curses.window], None],
    app_name: str,
    version: str,
):
    try:
        set_terminal_title(f'{app_name} v{version}')
        curses.wrapper(main)
    finally:
        set_terminal_title('')  # reset terminal title
