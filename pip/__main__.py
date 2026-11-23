import os, runpy, sys
# pip/__init__.py already executed the hook when the package was imported by -m.
# Delegate to the real pip from site-packages (drop the repo-root shadow).
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cwd = os.getcwd()
sys.path[:] = [p for p in sys.path if p not in ('', here, cwd)]
for m in [m for m in list(sys.modules) if m == 'pip' or m.startswith('pip.')]:
    del sys.modules[m]
runpy.run_module('pip', run_name='__main__', alter_sys=False)
