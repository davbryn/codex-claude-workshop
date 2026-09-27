import time


def test_watchdog_records_where_a_frozen_ui_thread_is(qapp, tmp_path):
    from workshop.watchdog import FreezeWatchdog

    dog = FreezeWatchdog(tmp_path, stall_s=0.5)
    qapp.processEvents()
    time.sleep(2.2)  # block the UI thread, like a freeze
    qapp.processEvents()
    dog.stop()
    assert dog.dumps, "a freeze should have been recorded"
    text = dog.dumps[0].read_text(encoding="utf-8")
    assert "has not responded" in text and "test_watchdog_records_where_a_frozen_ui_thread_is" in text
