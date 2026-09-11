from apps.worker.src import main, pipeline


class Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Connection(Transaction):
    def __init__(self, rows=None):
        self.executed = []
        self.rows = list(rows or [])

    def transaction(self):
        return Transaction()

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params))
        row = self.rows.pop(0) if self.rows else None
        return Result(row)


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


def test_once_without_handlers_does_not_claim_or_change_jobs(monkeypatch):
    monkeypatch.setattr(
        main,
        "claim_job",
        lambda *_args: (_ for _ in ()).throw(AssertionError("claim proibido")),
    )
    assert main.consume_once() == 0


def test_consume_once_delegates_only_supported_synthetic_fixture(monkeypatch):
    job = {
        "id": "00000000-0000-0000-0000-000000000001",
        "attempts": 1,
        "source_type": "synthetic",
    }
    handled = []
    claims = []

    def claim(worker_id, supported):
        claims.append((worker_id, supported))
        return job

    monkeypatch.setattr(main, "claim_job", claim)

    def fixture_handler(claimed, worker_id):
        handled.append((claimed["id"], worker_id))

    assert main.consume_once({"synthetic": fixture_handler}) == 0
    assert claims[0][1] == ("synthetic",)
    assert handled == [(job["id"], main.WORKER_ID)]


def test_worker_id_is_stable_across_polling(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "claim_job", lambda worker, _types: seen.append(worker))
    main.consume_once({"synthetic": lambda *_args: None})
    main.consume_once({"synthetic": lambda *_args: None})
    assert seen == [main.WORKER_ID, main.WORKER_ID]


def test_handler_failure_releases_lease_and_respects_attempt_limit(monkeypatch):
    connection = Connection()
    job = {
        "id": "00000000-0000-0000-0000-000000000001",
        "attempts": 5,
        "source_type": "synthetic",
    }
    monkeypatch.setattr(main, "claim_job", lambda _worker, _types: job)
    monkeypatch.setattr(main, "connect", lambda: connection)

    def failed_fixture_handler(_job, _worker_id):
        raise ValueError("fixture_failure")

    assert main.consume_once({"synthetic": failed_fixture_handler}) == 1
    update_sql, params = connection.executed[0]
    assert "lease_owner=NULL" in update_sql and "lease_expires_at=NULL" in update_sql
    assert params[:3] == ("failed", "failed", True)


def test_claim_job_filters_attempts_terminal_states_types_and_expired_leases(monkeypatch):
    queued = {"id": "job", "attempts": 4}
    claimed = {"id": "job", "attempts": 5, "source_type": "synthetic"}
    connection = Connection([queued, claimed, None])
    monkeypatch.setattr(pipeline, "connect", lambda: connection)
    assert pipeline.claim_job("stable-worker", ("synthetic",)) == claimed
    select_sql, select_params = connection.executed[0]
    assert "j.attempts < 5" in select_sql
    assert "lease_expires_at < CURRENT_TIMESTAMP" in select_sql
    assert "completed','failed','cancelled" in select_sql
    assert "s.source_type = ANY(%s)" in select_sql
    assert select_params == (["synthetic"],)
    update_sql, update_params = connection.executed[1]
    assert "attempts=attempts+1" in update_sql
    assert update_params[0] == "stable-worker"


def test_claim_job_with_no_supported_types_never_connects(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "connect",
        lambda: (_ for _ in ()).throw(AssertionError("conexão proibida")),
    )
    assert pipeline.claim_job("stable-worker", ()) is None
