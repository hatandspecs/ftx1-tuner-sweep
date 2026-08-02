"""Local browser GUI for sweeping a Yaesu FTX-1 across one or more bands and
triggering an external tuner (e.g. mAT-Tuner mAT-30) at each step, so it
builds up its per-frequency tuning memories on a new or different antenna.

Run with: python app.py
Then open http://127.0.0.1:5000

The page works whether or not the radio is connected - band/sweep settings
are always visible, and a background thread reports live connection status
(VFO, mode, power, tuner activity) once you connect. See docs/usage.md for
the physical setup and radio menu pre-flight checklist before running a
real sweep.
"""
import threading
import time
from dataclasses import dataclass, field

import serial
from flask import Flask, jsonify, render_template, request

from ftx1_cat import DEFAULT_LICENSE_ID, FTX1, frequencies_for, load_licenses

app = Flask(__name__)

POLL_INTERVAL_S = 1.0


@dataclass
class RadioState:
    lock: threading.RLock = field(default_factory=threading.RLock)
    radio: object = None
    port: str = ""
    baud: int = 38400
    connected: bool = False
    error: str = ""
    freq_hz: int = None
    power_w: int = None
    mode: str = None
    tuning: bool = None
    updated_at: float = 0.0


@dataclass
class SweepState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = False
    stop_requested: bool = False
    log: list = field(default_factory=list)
    total: int = 0
    done: int = 0
    error: str = ""


radio_state = RadioState()
sweep_state = SweepState()


def monitor_loop():
    while True:
        with radio_state.lock:
            radio = radio_state.radio
        if radio is None:
            time.sleep(0.3)
            continue
        try:
            freq = radio.read_frequency_hz()
            power = radio.read_power_w()
            mode = radio.read_mode()
            tuning = radio.tuner_is_tuning()
            with radio_state.lock:
                if radio_state.radio is radio:  # still the active connection
                    radio_state.freq_hz = freq
                    radio_state.power_w = power
                    radio_state.mode = mode
                    radio_state.tuning = tuning
                    radio_state.updated_at = time.time()
                    radio_state.connected = True
        except serial.SerialException as exc:
            with radio_state.lock:
                if radio_state.radio is radio:
                    radio_state.connected = False
                    radio_state.error = str(exc)
                    radio_state.radio = None
            try:
                radio.close()
            except Exception:
                pass
        time.sleep(POLL_INTERVAL_S)


threading.Thread(target=monitor_loop, daemon=True).start()


def run_sweep(freqs, settle_s, poll_s, dwell_s):
    try:
        for hz in freqs:
            if sweep_state.stop_requested:
                break

            with radio_state.lock:
                radio = radio_state.radio
            if radio is None:
                with sweep_state.lock:
                    sweep_state.error = "Radio disconnected during sweep."
                break

            radio.set_frequency_hz(hz)
            with sweep_state.lock:
                sweep_state.log.append({"freq_hz": hz, "status": "pending", "elapsed_s": None})
                row_index = len(sweep_state.log) - 1

            time.sleep(settle_s)
            radio.tuner_start()

            # dwell_s is a fixed wait, not an adaptive timeout: the FTX-1's
            # RI tuner-status flag doesn't reliably reflect completion for an
            # external tuner (the mAT-30 has no real feedback path back to
            # the radio), so we can't trust early-exit polling. We still poll
            # RI as a bonus - if it ever does report "stopped" early, we take
            # it - but the dwell itself is what you should actually tune.
            start = time.monotonic()
            status = "dwell"
            try:
                time.sleep(poll_s)
                while time.monotonic() - start < dwell_s:
                    if sweep_state.stop_requested:
                        status = "stopped"
                        break
                    tuning = radio.tuner_is_tuning()
                    if tuning is False:
                        status = "ok"
                        break
                    time.sleep(poll_s)
            finally:
                # Always leave the tuner ON (not bypassed), even if something
                # above raised - a half-finished step shouldn't strand the
                # radio without its tuner in circuit.
                radio.tuner_enable()

            elapsed = time.monotonic() - start
            with sweep_state.lock:
                sweep_state.log[row_index] = {
                    "freq_hz": hz, "status": status, "elapsed_s": round(elapsed, 1)
                }
                sweep_state.done += 1

            if status == "stopped":
                break
    except Exception as exc:
        with sweep_state.lock:
            sweep_state.error = str(exc)
    finally:
        with radio_state.lock:
            radio = radio_state.radio
        if radio is not None:
            try:
                radio.tuner_enable()
            except Exception:
                pass
        with sweep_state.lock:
            sweep_state.running = False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/licenses")
def licenses():
    # jsonify alphabetizes dict keys by default, which would silently
    # scramble band order (e.g. "6m" sorting before "80m"); band order is
    # sent as a list of {band, ranges} instead, since arrays aren't reordered.
    data = [
        {
            "license_id": lic["license_id"],
            "license_name": lic["license_name"],
            "country_group": lic["country_group"],
            "bands": [{"band": band, "ranges": ranges} for band, ranges in lic["bands"].items()],
        }
        for lic in load_licenses()
    ]
    return jsonify(licenses=data, default_license_id=DEFAULT_LICENSE_ID)


@app.route("/ports")
def ports():
    from serial.tools import list_ports

    return jsonify([p.device for p in list_ports.comports()])


@app.route("/connect", methods=["POST"])
def connect():
    payload = request.get_json(force=True)
    port = (payload.get("port") or "").strip()
    if not port:
        return jsonify(ok=False, error="Serial port is required."), 400
    try:
        baud = int(payload.get("baud", 38400))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Invalid baud rate."), 400

    with radio_state.lock:
        if radio_state.radio is not None:
            try:
                radio_state.radio.close()
            except Exception:
                pass
            radio_state.radio = None
            radio_state.connected = False

    try:
        radio = FTX1(port, baud)
        if not radio.ping():
            radio.close()
            with radio_state.lock:
                radio_state.error = "Connected to the port, but the radio didn't answer a CAT query."
            return jsonify(ok=False, error=radio_state.error), 502
    except serial.SerialException as exc:
        with radio_state.lock:
            radio_state.error = str(exc)
        return jsonify(ok=False, error=str(exc)), 400

    with radio_state.lock:
        radio_state.radio = radio
        radio_state.port = port
        radio_state.baud = baud
        radio_state.connected = True
        radio_state.error = ""

    return jsonify(ok=True)


@app.route("/disconnect", methods=["POST"])
def disconnect():
    with radio_state.lock:
        if radio_state.radio is not None:
            try:
                radio_state.radio.tuner_enable()
            except Exception:
                pass
            try:
                radio_state.radio.close()
            except Exception:
                pass
        radio_state.radio = None
        radio_state.connected = False
        radio_state.freq_hz = None
        radio_state.power_w = None
        radio_state.mode = None
        radio_state.tuning = None
    return jsonify(ok=True)


@app.route("/start", methods=["POST"])
def start():
    with sweep_state.lock:
        if sweep_state.running:
            return jsonify(ok=False, error="A sweep is already running."), 409

    with radio_state.lock:
        if radio_state.radio is None:
            return jsonify(ok=False, error="Connect to the radio first."), 409

    payload = request.get_json(force=True)

    try:
        step_hz = int(payload.get("step_hz", 10000))
        settle_s = float(payload.get("settle_ms", 300)) / 1000
        poll_s = float(payload.get("poll_ms", 300)) / 1000
        dwell_s = float(payload.get("dwell_s", 5))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Invalid numeric setting."), 400

    if step_hz <= 0:
        return jsonify(ok=False, error="Step must be positive."), 400

    ranges = []
    license_id = payload.get("license_id")
    requested_bands = payload.get("bands", [])
    if license_id and requested_bands:
        lic = next((l for l in load_licenses() if l["license_id"] == license_id), None)
        if lic is None:
            return jsonify(ok=False, error=f"Unknown license_id: {license_id!r}"), 400
        for band in requested_bands:
            ranges.extend(lic["bands"].get(band, []))

    for custom in payload.get("custom_ranges", []):
        custom = custom.strip()
        if not custom:
            continue
        try:
            lo_s, hi_s = custom.split("-")
            lo, hi = int(lo_s), int(hi_s)
        except ValueError:
            return (
                jsonify(ok=False, error=f"Bad custom range: {custom!r} (expected lo-hi in Hz)"),
                400,
            )
        if lo > hi:
            return jsonify(ok=False, error=f"Bad custom range: {custom!r} (lo > hi)"), 400
        ranges.append((lo, hi))

    if not ranges:
        return jsonify(ok=False, error="Select at least one band or custom range."), 400

    if not payload.get("confirmed"):
        return jsonify(ok=False, error="Pre-flight checklist not confirmed."), 400

    freqs = frequencies_for(ranges, step_hz)

    with sweep_state.lock:
        sweep_state.running = True
        sweep_state.stop_requested = False
        sweep_state.log = []
        sweep_state.total = len(freqs)
        sweep_state.done = 0
        sweep_state.error = ""

    thread = threading.Thread(
        target=run_sweep, args=(freqs, settle_s, poll_s, dwell_s), daemon=True
    )
    thread.start()
    return jsonify(ok=True, total=len(freqs))


@app.route("/stop", methods=["POST"])
def stop():
    with sweep_state.lock:
        sweep_state.stop_requested = True
    return jsonify(ok=True)


@app.route("/status")
def status():
    with radio_state.lock:
        radio_payload = dict(
            connected=radio_state.connected,
            port=radio_state.port,
            baud=radio_state.baud,
            error=radio_state.error,
            freq_hz=radio_state.freq_hz,
            power_w=radio_state.power_w,
            mode=radio_state.mode,
            tuning=radio_state.tuning,
            updated_at=radio_state.updated_at,
        )
    with sweep_state.lock:
        sweep_payload = dict(
            running=sweep_state.running,
            total=sweep_state.total,
            done=sweep_state.done,
            error=sweep_state.error,
            log=sweep_state.log,
        )
    return jsonify(radio=radio_payload, sweep=sweep_payload)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
