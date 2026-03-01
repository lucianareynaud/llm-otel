"""Retrieval service for RAG-augmented route handlers.

NOT YET IMPLEMENTED — no spec currently assigned.

If retrieval-augmented generation is added, this module will own document
retrieval using the document store in app.services.documents. It is scaffolded
here to reserve the location in the dependency graph.

Do not implement anything here until a spec with explicit tasks.md acceptance
criteria exists and its prerequisite gate is green.
"""


def retrieve(query: str, top_k: int = 5) -> list[str]:  # noqa: ARG001
    raise NotImplementedError("app.services.retrieval is not yet implemented")
