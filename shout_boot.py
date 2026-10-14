"""Packaged-build entry point, imported from Lib/site-packages/shout_boot.pth at interpreter start.

Shout.exe is the python.org-signed pythonw.exe, renamed (the signature stays valid, so Smart App Control
allows it). Started with no script argument, it runs the app here and exits before Python would read stdin.
"""
import os
import sys

if os.path.basename(sys.executable).lower() == 'shout.exe' and sys.argv in ([''], []):
    import logging
    try:
        import shout
        code = shout.main()
    except BaseException:
        logging.getLogger('shout').critical('startup failed', exc_info=True)
        code = 1
    logging.shutdown()
    os._exit(code or 0)
