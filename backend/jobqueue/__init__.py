"""Job queue package — DB persistence + threaded workers + REST routes.

Named `jobqueue` (not `queue`) to avoid shadowing Python stdlib's `queue`
module, which provides `queue.Queue` for the threaded worker.
"""
