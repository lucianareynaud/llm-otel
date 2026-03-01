"""Document store for retrieval-augmented generation.

NOT YET IMPLEMENTED — no spec currently assigned.

If retrieval-augmented generation is added to this project, this module will
own document ingestion, chunking, and storage. It is scaffolded here to reserve
the location in the dependency graph per the architecture steering doc.

Do not implement anything here until a spec with explicit tasks.md acceptance
criteria exists and its prerequisite gate is green.
"""


def get_document(doc_id: str) -> str:  # noqa: ARG001
    raise NotImplementedError("app.services.documents is not yet implemented")


def list_documents() -> list[str]:
    raise NotImplementedError("app.services.documents is not yet implemented")
