"""
FIFA World Cup 2026 Sweepstake — Flask Backend
Serves the app and exposes a JSON API backed by SQLite.
All state lives in sweepstake.db in the same directory.
"""

from flask import Flask, jsonify, request, render_template, abort, send_from_directory
import sqlite3, random, os, time

app = Flask(__name__)
DB  = os.path.join(os.path.dirname(__file__), 'sweepstake.db')

# ─────────────────────────────────────────
#  Database setup
# ─────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent readers
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS assignments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                participant TEXT    NOT NULL,
                team_name   TEXT    NOT NULL,
                created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS redraws (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                participant TEXT    NOT NULL,
                team_name   TEXT    NOT NULL,
                round       TEXT    NOT NULL,
                created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS points_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                participant TEXT    NOT NULL,
                event_label TEXT    NOT NULL,
                pts         INTEGER NOT NULL,
                round       TEXT    NOT NULL,
                team_name   TEXT,
                created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );
        """)

init_db()

# ─────────────────────────────────────────
#  Team data  (mirrors the JS TEAMS array)
# ─────────────────────────────────────────

TEAMS = [
    # Group A
    {"name":"United States","flag":"🇺🇸","group":"A"},
    {"name":"Panama","flag":"🇵🇦","group":"A"},
    {"name":"Morocco","flag":"🇲🇦","group":"A"},
    {"name":"Uruguay","flag":"🇺🇾","group":"A"},
    # Group B
    {"name":"Argentina","flag":"🇦🇷","group":"B"},
    {"name":"Chile","flag":"🇨🇱","group":"B"},
    {"name":"Peru","flag":"🇵🇪","group":"B"},
    {"name":"Australia","flag":"🇦🇺","group":"B"},
    # Group C
    {"name":"Mexico","flag":"🇲🇽","group":"C"},
    {"name":"Ecuador","flag":"🇪🇨","group":"C"},
    {"name":"Saudi Arabia","flag":"🇸🇦","group":"C"},
    {"name":"Senegal","flag":"🇸🇳","group":"C"},
    # Group D
    {"name":"France","flag":"🇫🇷","group":"D"},
    {"name":"Ukraine","flag":"🇺🇦","group":"D"},
    {"name":"Tunisia","flag":"🇹🇳","group":"D"},
    {"name":"Paraguay","flag":"🇵🇾","group":"D"},
    # Group E
    {"name":"Germany","flag":"🇩🇪","group":"E"},
    {"name":"Portugal","flag":"🇵🇹","group":"E"},
    {"name":"Hungary","flag":"🇭🇺","group":"E"},
    {"name":"South Africa","flag":"🇿🇦","group":"E"},
    # Group F
    {"name":"Brazil","flag":"🇧🇷","group":"F"},
    {"name":"Colombia","flag":"🇨🇴","group":"F"},
    {"name":"Venezuela","flag":"🇻🇪","group":"F"},
    {"name":"Japan","flag":"🇯🇵","group":"F"},
    # Group G
    {"name":"Canada","flag":"🇨🇦","group":"G"},
    {"name":"Nigeria","flag":"🇳🇬","group":"G"},
    {"name":"Honduras","flag":"🇭🇳","group":"G"},
    {"name":"Croatia","flag":"🇭🇷","group":"G"},
    # Group H
    {"name":"Spain","flag":"🇪🇸","group":"H"},
    {"name":"Serbia","flag":"🇷🇸","group":"H"},
    {"name":"Egypt","flag":"🇪🇬","group":"H"},
    {"name":"Bolivia","flag":"🇧🇴","group":"H"},
    # Group I
    {"name":"England","flag":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","group":"I"},
    {"name":"Netherlands","flag":"🇳🇱","group":"I"},
    {"name":"Algeria","flag":"🇩🇿","group":"I"},
    {"name":"South Korea","flag":"🇰🇷","group":"I"},
    # Group J
    {"name":"Italy","flag":"🇮🇹","group":"J"},
    {"name":"Belgium","flag":"🇧🇪","group":"J"},
    {"name":"New Zealand","flag":"🇳🇿","group":"J"},
    {"name":"Cameroon","flag":"🇨🇲","group":"J"},
    # Group K
    {"name":"Switzerland","flag":"🇨🇭","group":"K"},
    {"name":"Turkey","flag":"🇹🇷","group":"K"},
    {"name":"Costa Rica","flag":"🇨🇷","group":"K"},
    {"name":"Iran","flag":"🇮🇷","group":"K"},
    # Group L
    {"name":"Ivory Coast","flag":"🇨🇮","group":"L"},
    {"name":"Denmark","flag":"🇩🇰","group":"L"},
    {"name":"Uzbekistan","flag":"🇺🇿","group":"L"},
    {"name":"Ghana","flag":"🇬🇭","group":"L"},
]

TEAM_MAP = {t["name"]: t for t in TEAMS}

POINT_EVENTS = [
    {"label":"Team wins (group stage, 90 min)",    "pts": 3},
    {"label":"Team draws (group stage)",            "pts": 1},
    {"label":"Team qualifies from group stage",     "pts": 5},
    {"label":"Team keeps a clean sheet",            "pts": 2},
    {"label":"Team scores 3+ goals in a game",      "pts": 2},
    {"label":"Team wins a knockout game (90 min)",  "pts": 4},
    {"label":"Team wins via extra time",            "pts": 3},
    {"label":"Team wins a penalty shootout",        "pts": 2},
    {"label":"Team's player wins Man of the Match", "pts": 1},
    {"label":"Team reaches the semi-finals",        "pts": 5},
    {"label":"Team reaches the final",              "pts": 8},
    {"label":"Team wins the World Cup",             "pts":15},
    {"label":"Team concedes 3+ goals in a game",    "pts":-1},
    {"label":"Team gets a player sent off",         "pts":-1},
    {"label":"Team loses on penalties",             "pts":-1},
]

# ─────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────

def current_team(participant, db):
    """Most recent redraw team, or original assignment."""
    row = db.execute(
        "SELECT team_name FROM redraws WHERE participant=? ORDER BY created_at DESC LIMIT 1",
        (participant,)
    ).fetchone()
    if row:
        return row["team_name"]
    row = db.execute(
        "SELECT team_name FROM assignments WHERE participant=? ORDER BY created_at ASC LIMIT 1",
        (participant,)
    ).fetchone()
    return row["team_name"] if row else None

# ─────────────────────────────────────────
#  Routes — pages
# ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory("audio", filename)

# ─────────────────────────────────────────
#  API — teams & events (static data)
# ─────────────────────────────────────────

@app.route("/api/teams")
def api_teams():
    return jsonify(TEAMS)

@app.route("/api/events")
def api_events():
    return jsonify(POINT_EVENTS)

# ─────────────────────────────────────────
#  API — assignments (draw)
# ─────────────────────────────────────────

@app.route("/api/assignments")
def api_assignments():
    with get_db() as db:
        rows = db.execute(
            "SELECT participant, team_name FROM assignments ORDER BY created_at ASC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/assignments", methods=["POST"])
def api_add_assignment():
    data = request.get_json(force=True)
    participant = (data.get("participant") or "").strip()
    if not participant:
        return jsonify({"error": "participant required"}), 400

    with get_db() as db:
        # Work out available pool
        assigned = {r["team_name"] for r in db.execute(
            "SELECT team_name FROM assignments"
        ).fetchall()}
        pool = [t["name"] for t in TEAMS if t["name"] not in assigned]
        if not pool:
            pool = [t["name"] for t in TEAMS]   # bonus round

        picked = random.choice(pool)
        db.execute(
            "INSERT INTO assignments (participant, team_name) VALUES (?,?)",
            (participant, picked)
        )

    team = TEAM_MAP[picked]
    return jsonify({"participant": participant, "team": team})

@app.route("/api/assignments/reset", methods=["POST"])
def api_reset():
    with get_db() as db:
        db.execute("DELETE FROM assignments")
        db.execute("DELETE FROM redraws")
        db.execute("DELETE FROM points_log")
    return jsonify({"ok": True})

# ─────────────────────────────────────────
#  API — points
# ─────────────────────────────────────────

@app.route("/api/points")
def api_points():
    """Returns leaderboard: [{participant, pts, team, redraw_count}]"""
    with get_db() as db:
        participants = [r["participant"] for r in db.execute(
            "SELECT DISTINCT participant FROM assignments ORDER BY participant"
        ).fetchall()]

        rows = db.execute(
            "SELECT participant, SUM(pts) as total FROM points_log GROUP BY participant"
        ).fetchall()
        pts_map = {r["participant"]: r["total"] for r in rows}

        redraw_count = db.execute(
            "SELECT participant, COUNT(*) as cnt FROM redraws GROUP BY participant"
        ).fetchall()
        rd_map = {r["participant"]: r["cnt"] for r in redraw_count}

        result = []
        for p in participants:
            team_name = current_team(p, db)
            team_obj  = TEAM_MAP.get(team_name) if team_name else None
            result.append({
                "participant":   p,
                "pts":           pts_map.get(p, 0),
                "team":          team_obj,
                "redraw_count":  rd_map.get(p, 0),
            })

    result.sort(key=lambda x: (-x["pts"], x["participant"]))
    return jsonify(result)

@app.route("/api/points/log", methods=["POST"])
def api_log_points():
    data        = request.get_json(force=True)
    participant = (data.get("participant") or "").strip()
    event_idx   = data.get("event_index")
    round_name  = (data.get("round") or "").strip()

    if not participant or event_idx is None or not round_name:
        return jsonify({"error": "participant, event_index and round required"}), 400
    if not isinstance(event_idx, int) or not (0 <= event_idx < len(POINT_EVENTS)):
        return jsonify({"error": "invalid event_index"}), 400

    event = POINT_EVENTS[event_idx]
    with get_db() as db:
        team_name = current_team(participant, db)
        db.execute(
            "INSERT INTO points_log (participant, event_label, pts, round, team_name) VALUES (?,?,?,?,?)",
            (participant, event["label"], event["pts"], round_name, team_name)
        )
    return jsonify({"ok": True, "pts": event["pts"]})

@app.route("/api/points/history")
def api_points_history():
    with get_db() as db:
        rows = db.execute(
            "SELECT participant, event_label, pts, round, team_name, created_at "
            "FROM points_log ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/points/history/<int:entry_id>", methods=["DELETE"])
def api_delete_history_entry(entry_id):
    with get_db() as db:
        row = db.execute("SELECT pts, participant FROM points_log WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        db.execute("DELETE FROM points_log WHERE id=?", (entry_id,))
    return jsonify({"ok": True})

@app.route("/api/points/reset", methods=["POST"])
def api_reset_points():
    with get_db() as db:
        db.execute("DELETE FROM points_log")
        db.execute("DELETE FROM redraws")
    return jsonify({"ok": True})

# ─────────────────────────────────────────
#  API — re-draws
# ─────────────────────────────────────────

@app.route("/api/redraws", methods=["POST"])
def api_add_redraw():
    data        = request.get_json(force=True)
    participant = (data.get("participant") or "").strip()
    team_name   = (data.get("team_name")   or "").strip()
    round_name  = (data.get("round")       or "").strip()

    if not participant or not team_name or not round_name:
        return jsonify({"error": "participant, team_name and round required"}), 400
    if team_name not in TEAM_MAP:
        return jsonify({"error": "unknown team"}), 400

    with get_db() as db:
        db.execute(
            "INSERT INTO redraws (participant, team_name, round) VALUES (?,?,?)",
            (participant, team_name, round_name)
        )
        # Also log in history as a zero-point event
        db.execute(
            "INSERT INTO points_log (participant, event_label, pts, round, team_name) VALUES (?,?,?,?,?)",
            (participant, f"🔄 Re-draw → {team_name}", 0, round_name, team_name)
        )

    return jsonify({"ok": True, "team": TEAM_MAP[team_name]})

# ─────────────────────────────────────────
#  Run
# ─────────────────────────────────────────

if __name__ == "__main__":
    # 0.0.0.0 makes the server reachable from other machines on the LAN
    app.run(host="0.0.0.0", port=5000, debug=True)
