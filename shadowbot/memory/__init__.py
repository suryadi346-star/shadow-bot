"""
ShadowBot Memory System
Inspired by nanobot's Dream two-stage memory architecture
- Short-term: current conversation (in-memory list di agent loop)
- Long-term: SQLite + BM25 search (Termux-safe, no heavy ML needed)
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class MemoryDB:
    """
    Persistent memory store — SQLite backend + BM25 search
    Stores conversation summaries dan important facts
    """

    def __init__(self, db_path: str = "~/.shadowbot/memory.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._bm25 = None
        self._bm25_docs = []
        self._rebuild_index()

    def _init_db(self):
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                session TEXT NOT NULL,
                user_msg TEXT NOT NULL,
                assistant_msg TEXT NOT NULL,
                summary TEXT,
                tags TEXT
            )
        """)
        # FTS5 virtual table for fast text search
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(
                user_msg,
                assistant_msg,
                summary,
                content=memories,
                content_rowid=id
            )
        """)
        self.conn.commit()

    def _rebuild_index(self):
        """Rebuild BM25 index from database"""
        try:
            from rank_bm25 import BM25Okapi
            rows = self.conn.execute(
                "SELECT id, user_msg, summary FROM memories ORDER BY id DESC LIMIT 500"
            ).fetchall()
            if rows:
                self._bm25_docs = rows
                corpus = []
                for row in rows:
                    text = f"{row[1]} {row[2] or ''}"
                    corpus.append(text.lower().split())
                self._bm25 = BM25Okapi(corpus)
        except ImportError:
            self._bm25 = None

    async def save_turn(self, user_msg: str, assistant_msg: str, session: str = "default"):
        """Save a conversation turn to memory"""
        now = datetime.now().isoformat(timespec="seconds")
        # Generate a quick summary (first 200 chars of exchange)
        summary = f"{user_msg[:100]} → {assistant_msg[:100]}"
        self.conn.execute(
            """INSERT INTO memories (date, session, user_msg, assistant_msg, summary)
               VALUES (?, ?, ?, ?, ?)""",
            (now, session, user_msg, assistant_msg, summary),
        )
        self.conn.commit()
        # Rebuild BM25 every 10 saves
        total = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        if total % 10 == 0:
            self._rebuild_index()

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Search memories by BM25 or FTS5 fallback"""
        results = []

        # Try BM25 first
        if self._bm25 and self._bm25_docs:
            try:
                tokens = query.lower().split()
                scores = self._bm25.get_scores(tokens)
                top_indices = sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )[:top_k]
                for idx in top_indices:
                    if scores[idx] > 0:
                        row = self._bm25_docs[idx]
                        results.append({
                            "date": "recent",
                            "content": f"Q: {row[1]}\nSummary: {row[2] or ''}",
                            "score": float(scores[idx]),
                        })
                if results:
                    return results
            except Exception:
                pass

        # FTS5 fallback
        try:
            rows = self.conn.execute(
                """SELECT m.date, m.user_msg, m.assistant_msg, m.summary
                   FROM memories_fts f
                   JOIN memories m ON f.rowid = m.id
                   WHERE memories_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, top_k),
            ).fetchall()
            for row in rows:
                results.append({
                    "date": row[0],
                    "content": f"Q: {row[1]}\nA: {row[2][:200]}",
                    "score": 1.0,
                })
        except Exception:
            # Plain LIKE fallback
            rows = self.conn.execute(
                """SELECT date, user_msg, assistant_msg
                   FROM memories
                   WHERE user_msg LIKE ? OR assistant_msg LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", top_k),
            ).fetchall()
            for row in rows:
                results.append({
                    "date": row[0],
                    "content": f"Q: {row[1]}\nA: {row[2][:200]}",
                    "score": 0.5,
                })

        return results

    def get_context(self, max_items: int = 5) -> str:
        """Get recent memories as context string for system prompt"""
        rows = self.conn.execute(
            "SELECT date, summary FROM memories ORDER BY id DESC LIMIT ?",
            (max_items,),
        ).fetchall()
        if not rows:
            return ""
        lines = [f"- [{r[0]}] {r[1]}" for r in reversed(rows)]
        return "Recent conversation history:\n" + "\n".join(lines)

    def get_all(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, date, session, user_msg, summary FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "date": r[1], "session": r[2], "user": r[3], "summary": r[4]}
            for r in rows
        ]

    def clear(self):
        self.conn.execute("DELETE FROM memories")
        self.conn.execute("DELETE FROM memories_fts")
        self.conn.commit()
        self._bm25 = None
        self._bm25_docs = []

    def close(self):
        self.conn.close()
