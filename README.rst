|pypi| |github|

bookmarks-curses
================

bookmarks-curses is a bookmark manager as a curses frontend to SQLite database.

Editing a record is done with Vim, using a temporary file located in /dev/shm. To launch a URL, xdg-open is used, while copying to the clipboard is handled by xsel.
To display a URL as a QR code in the terminal, the `qrencode`_ command is used.

The current hotkeys are:
    * h: help screen
    * q, Esc: Quit the program
    * j, Down: Move selection down
    * k, Up: Move selection up
    * PgUp: Page up
    * PgDown: Page down
    * g, Home: Move to first item
    * G, End: Move to last item
    * Alt-{m,c,t,u}: Sort by modtime, created, title, URL
    * Delete: Delete current record
    * Insert: Insert record
    * e: Edit current record
    * L: Launch URL
    * I: Import html (Diigo export Chrome)
    * s: Search records
    * D: Show/hide deleted records
    * U: Show URL as QR-code
    * Ctrl-L: Copy URL to clipboard
    * Ctrl-T: Copy Title to clipboard

.. |pypi| image:: https://img.shields.io/pypi/v/bookmarks-curses
          :target: https://pypi.org/project/bookmarks-curses/
.. |github| image:: https://img.shields.io/github/v/tag/shamilbi/bookmarks-curses?label=github
            :target: https://github.com/shamilbi/bookmarks-curses/
.. _qrencode: https://github.com/fukuchi/libqrencode
