"""WhatsApp the admin when a scheduled ops job fails (backup, restore drill, cold export).

systemd starts this through jobshub-alert-admin@<failed unit>.service, which each ops unit
names in OnFailure=. It sends one message -- the unit, the host, the time and the last lines
of backup.log -- to ADMIN_ALERT_WHATSAPP only, through the same whatsapp-sender gateway the
alert digests use. Site users never get these.

    python -m jobhub_poc.ops.alert_admin jobshub-backup.service
"""
import socket
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

from jobhub_poc import config
from jobhub_poc.alerts.senders import LiveSender
from jobhub_poc.phone import normalize_e164

LOG_PATH = Path(__file__).resolve().parents[2] / "backup.log"
_TAIL_LINES = 8
_MAX_LINE = 160


def build_message(unit, host, when, log_lines):
    lines = [f"JobsHub ops alert: {unit} FAILED on {host} at {when:%Y-%m-%d %H:%M}."]
    if log_lines:
        lines += ["", "Last log lines:"]
        lines += [line[:_MAX_LINE] for line in log_lines]
    lines += ["", f"Check: systemctl --user status {unit}"]
    return "\n".join(lines)


def tail(path, n=_TAIL_LINES):
    try:
        with open(path, errors="replace") as f:
            return [line.rstrip("\n") for line in deque(f, maxlen=n) if line.strip()]
    except OSError:
        return []


def send_alert(unit, sender, phone, log_path=LOG_PATH, host=None, now=None):
    """Sends the alert; returns the text sent. Raises if no valid admin number is set."""
    number = normalize_e164(phone)
    if not number:
        raise RuntimeError("ADMIN_ALERT_WHATSAPP is not set to a +<country code><number>")
    text = build_message(unit, host or socket.gethostname(), now or datetime.now(), tail(log_path))
    sender.whatsapp(number, text)
    return text


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python -m jobhub_poc.ops.alert_admin <failed unit>")
    try:
        send_alert(sys.argv[1], LiveSender(), config.ADMIN_ALERT_WHATSAPP)
    except Exception as exc:  # the failure itself is already in the journal; say why we couldn't tell anyone
        sys.exit(f"admin alert for {sys.argv[1]} not sent: {exc}")
    print(f"admin alert sent for {sys.argv[1]}")


if __name__ == "__main__":
    main()
