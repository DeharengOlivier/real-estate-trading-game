"""Parameters of the simulated housing market.

These are the model, not the seeding: the coefficients that turn macro and
local indices into a price, the zones, the renovation catalog and the starting
capital. The API prices with them on every request and the seed generates the
initial world from them, so they belong to neither and are imported by both.

They lived in ``seed/constants.py``, which the API reached by inserting the
project root into ``sys.path`` at import time. The path entry was unnecessary
(both packages sit at the root, and both images have it as their working
directory) and it named the dependency backwards: business logic does not
depend on a script.
"""
