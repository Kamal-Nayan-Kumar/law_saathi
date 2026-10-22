"""Law Saathi realtime voice agent (LiveKit worker).

Importing the package loads `api/.env`, so every module in it can rely on the
keys being in the environment. The Sarvam plugin reads SARVAM_API_KEY from the
environment itself, so this is what makes that plugin work without every
call site passing the key around.
"""
from . import config  # noqa: F401
