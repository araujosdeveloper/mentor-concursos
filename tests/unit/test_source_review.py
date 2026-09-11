import uuid

import pytest
from fastapi import HTTPException

from apps.api.src.knowledge_review import review_knowledge_version

SOURCE_ID = uuid.UUID(int=1)
VERSION_ID = uuid.UUID(int=2)
REVIEWER_ID = uuid.UUID(int=3)
OTHER_ID = uuid.UUID(int=99)
OLD_VERSION_ID = uuid.UUID(int=5)


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(
        self,
        *,
        role="source_reviewer",
        owner=REVIEWER_ID,
        status="pending_review",
        chunks=None,
        previous=None,
        reviews=None,
    ):
        self.role = role
        self.owner = owner
        self.status = status
        self.chunks = chunks if chunks is not None else [self.chunk()]
        self.previous = previous or []
        self.reviews = reviews or []
        self.queries = []

    @staticmethod
    def chunk(**changes):
        row = {
            "id": uuid.UUID(int=10),
            "status": "pending_review",
            "metadata": {"prompt_injection_suspected": False},
            "approved_embedding": True,
        }
        row.update(changes)
        return row

    @property
    def mutations(self):
        return [sql for sql, _ in self.queries if sql.startswith(("INSERT", "UPDATE", "DELETE"))]

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.queries.append((normalized, params))
        if normalized.startswith("SELECT v.*"):
            return Result(
                {
                    "id": VERSION_ID,
                    "source_id": SOURCE_ID,
                    "status": self.status,
                    "source_status": "approved" if self.status == "indexed" else "pending_review",
                    "owner_user_id": self.owner,
                    "role": self.role,
                }
            )
        if normalized.startswith("SELECT * FROM mentor_concursos.source_reviews"):
            return Result(rows=self.reviews)
        if normalized.startswith("SELECT c.id"):
            return Result(rows=self.chunks)
        if normalized.startswith("SELECT status FROM mentor_concursos.knowledge_chunks"):
            expected = "indexed" if self.status == "indexed" else "rejected"
            return Result(rows=[{"status": expected}])
        if normalized.startswith("SELECT id FROM mentor_concursos.knowledge_source_versions"):
            return Result(rows=self.previous)
        if normalized.startswith("INSERT INTO mentor_concursos.source_reviews"):
            return Result({"id": uuid.UUID(int=4), "decision": params[3]})
        return Result()


def review(connection, decision="approved"):
    return review_knowledge_version(
        connection,
        version_id=VERSION_ID,
        reviewer_id=REVIEWER_ID,
        decision=decision,
        reason="fixture sintética",
        request_id="fixture-review",
    )


@pytest.mark.parametrize("role", ["student", "operator"])
def test_student_and_operator_cannot_review(role):
    with pytest.raises(HTTPException) as error:
        review(FakeConnection(role=role))
    assert error.value.status_code == 403


def test_source_reviewer_only_reviews_own_source():
    with pytest.raises(HTTPException) as error:
        review(FakeConnection(owner=OTHER_ID))
    assert error.value.status_code == 404
    assert review(FakeConnection())["decision"] == "approved"


def test_admin_can_review_any_source():
    assert review(FakeConnection(role="admin", owner=OTHER_ID))["decision"] == "approved"


def test_approval_promotes_all_entities_and_supersedes_previous_version():
    connection = FakeConnection(previous=[{"id": OLD_VERSION_ID}])
    assert review(connection)["decision"] == "approved"
    statements = "\n".join(connection.mutations)
    assert "source_reviews" in statements
    assert "knowledge_chunks SET status='indexed'" in statements
    assert "knowledge_source_versions SET status='indexed'" in statements
    assert "knowledge_sources SET status='approved'" in statements
    assert "knowledge_chunks SET status='rejected'" in statements
    assert "knowledge_source_versions SET status='superseded'" in statements
    assert "audit_events" in statements
    assert "ingestion_events" in statements


@pytest.mark.parametrize("reason", ["missing", "wrong_dimensions", "wrong_revision"])
def test_missing_or_incompatible_embedding_blocks_approval(reason):
    connection = FakeConnection(chunks=[FakeConnection.chunk(approved_embedding=False)])
    with pytest.raises(HTTPException, match="Embedding"):
        review(connection)
    assert connection.mutations == []


def test_prompt_injection_suspicion_blocks_approval_without_partial_state():
    connection = FakeConnection(
        chunks=[FakeConnection.chunk(metadata={"prompt_injection_suspected": True})]
    )
    with pytest.raises(HTTPException, match="suspeito"):
        review(connection)
    assert connection.mutations == []


@pytest.mark.parametrize("chunks", [[], [FakeConnection.chunk(status="indexed")]])
def test_approval_requires_nonempty_entirely_pending_chunks(chunks):
    connection = FakeConnection(chunks=chunks)
    with pytest.raises(HTTPException):
        review(connection)
    assert connection.mutations == []


def test_rejection_preserves_previously_indexed_version():
    connection = FakeConnection(previous=[{"id": OLD_VERSION_ID}])
    assert review(connection, "rejected")["decision"] == "rejected"
    statements = "\n".join(connection.mutations)
    assert "knowledge_source_versions SET status='rejected' WHERE id=%s" in statements
    assert "status='superseded'" not in statements
    assert "knowledge_sources SET status='rejected'" not in statements


def test_exact_approval_retry_is_idempotent_and_does_not_duplicate_review():
    existing = {"id": uuid.UUID(int=4), "decision": "approved"}
    connection = FakeConnection(status="indexed", reviews=[existing])
    assert review(connection) == existing
    assert connection.mutations == []


def test_conflicting_decision_returns_409():
    connection = FakeConnection(
        status="indexed", reviews=[{"id": uuid.UUID(int=4), "decision": "approved"}]
    )
    with pytest.raises(HTTPException) as error:
        review(connection, "rejected")
    assert error.value.status_code == 409


def test_rejected_or_superseded_version_cannot_be_approved():
    for status in ("rejected", "superseded"):
        with pytest.raises(HTTPException) as error:
            review(FakeConnection(status=status))
        assert error.value.status_code == 409
