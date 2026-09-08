"""Hearback API sidecar.

The sidecar owns the canonical truth state. The voice agent and the dashboard are both clients:
the agent posts utterances, extraction requests and ledger cuts, the dashboard reads state and
subscribes to the event stream. One owner means one epoch counter and one relay gate.
"""
