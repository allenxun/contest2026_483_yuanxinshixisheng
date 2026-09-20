"""Medical-platform internal AI API (protocol 1.0).

Kept separate from the web-facing routes on purpose: this package never reuses
the end-user token flow, the web chat session tables or the legacy
``/chat/knowledge_base_chat`` protocol.
"""

from server.internal_ai.routes import router as internal_ai_router

__all__ = ["internal_ai_router"]
