"""
ShadowBot RAG Engine
Inspired by Project NOMAD's knowledge base + Qdrant RAG pipeline
Implementasi ringan: SQLite + BM25 (no Docker, no heavy ML, Termux-compatible)
"""
import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional


class RAGEngine:
    """
    Lightweight offline knowledge base.
    Store documents → BM25 search → inject as context.
    No embeddings server needed — pure SQLite + BM25.
    """

    def __init__(self, db_path: str = "~/.shadowbot/knowledge.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._bm25 = None
        self._bm25_docs = []
        self._rebuild_index()

    def _init_db(self):
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                added_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        # FTS5 untuk full-text search
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(
                title,
                content,
                content=documents,
                content_rowid=id
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source ON documents(source)
        """)
        self.conn.commit()

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks"""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks if chunks else [text]

    def add_document(
        self,
        content: str,
        source: str = "manual",
        title: str = "",
        metadata: dict = None,
    ) -> int:
        """Add a document to the knowledge base (auto-chunked)"""
        chunks = self._chunk_text(content)
        added = 0

        for i, chunk in enumerate(chunks):
            doc_hash = hashlib.md5(f"{source}:{i}:{chunk[:100]}".encode()).hexdigest()
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO documents
                       (hash, source, title, content, chunk_index, added_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc_hash,
                        source,
                        title or source,
                        chunk,
                        i,
                        datetime.now().isoformat(timespec="seconds"),
                        json.dumps(metadata or {}),
                    ),
                )
                added += 1
            except sqlite3.IntegrityError:
                pass  # Already exists

        self.conn.commit()
        self._rebuild_index()
        return added

    def add_file(self, file_path: str) -> str:
        """Add a text file to the knowledge base"""
        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Error: file not found: {file_path}"
        if not p.is_file():
            return f"Error: not a file: {file_path}"

        try:
            content = p.read_text(errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        if len(content.strip()) == 0:
            return "Error: file is empty"

        added = self.add_document(
            content=content,
            source=str(p),
            title=p.name,
        )
        return f"✓ Added {added} chunks from '{p.name}'"

    def _rebuild_index(self):
        """Rebuild BM25 index"""
        try:
            from rank_bm25 import BM25Okapi
            rows = self.conn.execute(
                "SELECT id, source, title, content FROM documents ORDER BY id DESC LIMIT 2000"
            ).fetchall()
            if rows:
                self._bm25_docs = rows
                corpus = []
                for row in rows:
                    text = f"{row[2] or ''} {row[3]}"
                    corpus.append(text.lower().split())
                self._bm25 = BM25Okapi(corpus)
        except ImportError:
            self._bm25 = None

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Search knowledge base — BM25 → FTS5 fallback"""
        results = []

        # BM25 search
        if self._bm25 and self._bm25_docs:
            try:
                tokens = query.lower().split()
                scores = self._bm25.get_scores(tokens)
                top_indices = sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )[:top_k]
                for idx in top_indices:
                    if scores[idx] > 0.01:
                        row = self._bm25_docs[idx]
                        results.append({
                            "id": row[0],
                            "source": row[1],
                            "title": row[2] or row[1],
                            "content": row[3],
                            "score": float(scores[idx]),
                        })
                if results:
                    return results
            except Exception:
                pass

        # FTS5 fallback
        try:
            rows = self.conn.execute(
                """SELECT d.id, d.source, d.title, d.content
                   FROM documents_fts f
                   JOIN documents d ON f.rowid = d.id
                   WHERE documents_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, top_k),
            ).fetchall()
            for row in rows:
                results.append({
                    "id": row[0],
                    "source": row[1],
                    "title": row[2] or row[1],
                    "content": row[3],
                    "score": 1.0,
                })
        except Exception:
            # LIKE fallback
            rows = self.conn.execute(
                """SELECT id, source, title, content FROM documents
                   WHERE content LIKE ? OR title LIKE ?
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", top_k),
            ).fetchall()
            for row in rows:
                results.append({
                    "id": row[0],
                    "source": row[1],
                    "title": row[2] or row[1],
                    "content": row[3],
                    "score": 0.3,
                })

        return results

    def list_sources(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT source, title, COUNT(*) as chunks, MIN(added_at) as added
               FROM documents GROUP BY source ORDER BY added DESC"""
        ).fetchall()
        return [{"source": r[0], "title": r[1], "chunks": r[2], "added": r[3]} for r in rows]

    def delete_source(self, source: str) -> str:
        c = self.conn.execute("DELETE FROM documents WHERE source = ?", (source,))
        self.conn.commit()
        self._rebuild_index()
        return f"✓ Deleted {c.rowcount} chunks from '{source}'"

    def stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        sources = self.conn.execute("SELECT COUNT(DISTINCT source) FROM documents").fetchone()[0]
        return {"total_chunks": total, "total_sources": sources}

    def close(self):
        self.conn.close()
