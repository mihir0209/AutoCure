import pytest
from healing.shelve_marshal_defusal_healer import ShelveMarshalDefusalHealer
from healing.flask_debug_production_guard import FlaskDebugProductionGuard
from healing.sqlite_format_injection_healer import SqliteFormatInjectionHealer
from healing.threading_mutex_deadlock_healer import ThreadingMutexDeadlockHealer
from healing.tempfile_fd_leak_healer import TempfileFdLeakHealer

def test_achievement_1_shelve_marshal_defusal():
    healer = ShelveMarshalDefusalHealer()
    code = "import marshal\ndata = marshal.loads(payload)"
    healed, count = healer.heal_source(code)
    assert count >= 1
    assert "import json" in healed
    assert "json.loads" in healed

def test_achievement_2_flask_debug_guard():
    healer = FlaskDebugProductionGuard()
    code = "app.run(host='0.0.0.0', port=5000, debug=True)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "debug=False" in healed

def test_achievement_3_sqlite_format_injection():
    healer = SqliteFormatInjectionHealer()
    code = 'cursor.execute(f"SELECT * FROM users WHERE id = \'{user_id}\'")'
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "WHERE id = ?" in healed
    assert "user_id" in healed

def test_achievement_4_threading_mutex_healer():
    healer = ThreadingMutexDeadlockHealer()
    code = "lock = threading.Lock()"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "threading.RLock()" in healed

def test_achievement_5_tempfile_fd_leak_healer():
    healer = TempfileFdLeakHealer()
    code = "fd, path = tempfile.mkstemp()"
    healed, count = healer.heal_source(code)
    assert count == 1
