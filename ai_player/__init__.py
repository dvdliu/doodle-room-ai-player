"""An AI player for Doodle Room's Pictionary game (com.pictionary.PictionaryServer).

Connects to a running PictionaryServer as a regular WebSocket player and plays both
roles. It guesses other players' drawings from a live-rendered canvas snapshot, and
sketches its own turn from an AI-generated stroke plan.
"""

__version__ = "0.1.0"
