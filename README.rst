|pypi| |github|

bookmarks-curses
================

bookmarks-curses is a bookmark manager as a curses frontend to SQLite database.

It uses external utilities:
    * vim - to edit a record (using an anonymous file in memory)
    * xdg-open - to launch a URL
    * xsel - to copy to the clipboard
    * `qrencode`_ - to display a URL as a QR code
    * dd - to fill a file in memory by zeros

Search string may contain word -#tag to exclude tag #tag from the search result.

If you'd like to store your bookmarks file in an encrypted directory, you can create one using the command `cryfs`_

.. code:: bash

   cryfs -o noatime dir mountpoint

and place your file in mountpoint/.

The current hotkeys are:
    * F1: help screen
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
    * Ctrl-G: Copy Tags to clipboard

.. |pypi| image:: https://img.shields.io/pypi/v/bookmarks-curses
          :target: https://pypi.org/project/bookmarks-curses/
.. |github| image:: https://img.shields.io/github/v/tag/shamilbi/bookmarks-curses?label=github
            :target: https://github.com/shamilbi/bookmarks-curses/
.. _qrencode: https://github.com/fukuchi/libqrencode
.. _cryfs: https://github.com/cryfs/cryfs
