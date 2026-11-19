"""Debug mode of the port (command line `--debug`, or `launch_debug.bat`): nothing here runs without it.

- `service`: the debug service owned by the window (Game.debug): time control (pause, one engine step, slower / faster), the overlay, the commands of the other tools,
  all applied between two engine steps on the window's thread (the engine is never touched from another thread).
"""
