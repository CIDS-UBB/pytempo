"""FUTURE, optional: natural language discovery. The AI mode.

The idea: 'I want statistics about unemployment' gives a list of candidate
indicators, by matching the request against the matrix index with the help of a
model.

Deliberately isolated here so the core picks up NO AI dependencies. Off by
default. The model (the Anthropic API, or a local one) would be configurable,
never imposed.
"""


def discover(query: str, client=None, limit: int = 10) -> list:
    """Return candidate indicators for a natural language request.

    Not implemented: a seam for later. The core works fully without it.
    """
    raise NotImplementedError("future, optional: AI mode")
