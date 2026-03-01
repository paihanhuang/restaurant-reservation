-- 001_init.sql — Initial schema for reservation agent
-- SQLite schema: reservations, transcript_turns, call_logs, state_transitions

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    restaurant_name TEXT NOT NULL,
    restaurant_phone TEXT NOT NULL,
    date TEXT NOT NULL,
    preferred_time TEXT NOT NULL,
    alt_time_start TEXT,
    alt_time_end TEXT,
    party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 20),
    special_requests TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    call_attempts INTEGER NOT NULL DEFAULT 0,
    call_sid TEXT,
    confirmed_time TEXT,
    user_phone TEXT NOT NULL DEFAULT '',
    user_email TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcript_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id TEXT NOT NULL REFERENCES reservations(reservation_id),
    call_sid TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('restaurant', 'agent')),
    text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id TEXT NOT NULL REFERENCES reservations(reservation_id),
    call_sid TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    duration_seconds INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id TEXT NOT NULL REFERENCES reservations(reservation_id),
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    trigger TEXT NOT NULL,
    call_sid TEXT,
    timestamp TEXT NOT NULL
);

-- View: full transcript as text for backward compatibility
CREATE VIEW IF NOT EXISTS transcript_view AS
SELECT reservation_id,
       GROUP_CONCAT(role || ': ' || text, CHAR(10)) AS full_transcript
FROM transcript_turns
GROUP BY reservation_id
ORDER BY turn_number;
