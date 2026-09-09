import os
import time
from flask import Flask, jsonify, request
import psycopg2

app = Flask(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db(retries=10, delay=2):
    for attempt in range(retries):
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        done BOOLEAN DEFAULT FALSE
                    )
                """)
            print("DB initialized", flush=True)
            return
        except psycopg2.OperationalError as e:
            print(f"DB not ready ({attempt + 1}/{retries}): {e}", flush=True)
            time.sleep(delay)
    raise RuntimeError("Database unavailable after retries")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/ready")
def ready():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify(status="ready")
    except Exception as e:
        return jsonify(status="not ready", error=str(e)), 503


@app.get("/api/items")
def list_items():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, done FROM items ORDER BY id")
        rows = cur.fetchall()
    return jsonify([{"id": r[0], "name": r[1], "done": r[2]} for r in rows])


@app.post("/api/items")
def create_item():
    name = request.json["name"]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO items (name) VALUES (%s) RETURNING id", (name,))
        item_id = cur.fetchone()[0]
    return jsonify(id=item_id, name=name), 201


@app.patch("/api/items/<int:item_id>")
def toggle_item(item_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE items SET done = NOT done WHERE id = %s RETURNING id, name, done",
            (item_id,),
        )
        row = cur.fetchone()
    if row is None:
        return jsonify(error="not found"), 404
    return jsonify(id=row[0], name=row[1], done=row[2])


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
