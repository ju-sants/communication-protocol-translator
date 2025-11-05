from datetime import datetime, timezone, timedelta

def is_signal_fail(timestamp_str: str):
    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")
    timestamp = timestamp.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - timestamp >= timedelta(hours=24):
        return True
    else:
        return False