import pytest
import threading
import core.database as db


@pytest.mark.tier2
class TestConnectionStorm:
    def test_500_concurrent_queries(self):
        errors = []

        def query():
            try:
                conn = db.get_db()
                db._fetchone(conn, "SELECT 1")
                conn.close()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=query) for _ in range(500)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_concurrent_writes_same_article(self):
        conn = db.get_db()
        article = db.create_article("Concurrent Test", "Initial content", "test")
        assert article is not None
        conn.close()

        errors = []

        def update():
            try:
                db.update_article(article["id"], "Updated content", "test")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=update) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


@pytest.mark.tier2
class TestCorruptDB:
    def test_corrupt_database_handling(self, monkeypatch):
        import sqlite3
        def broken_connect(path, **kw):
            raise sqlite3.DatabaseError("database disk image is malformed")
        monkeypatch.setattr(sqlite3, "connect", broken_connect)
        with pytest.raises(sqlite3.DatabaseError):
            db.get_db()


@pytest.mark.tier2
class TestExtremeSlug:
    def test_extremely_long_title(self):
        title = "A" * 10_000
        slug = db.slugify(title)
        assert len(slug) > 0
        assert slug == "a" * 10_000
