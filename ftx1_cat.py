"""CAT control for a Yaesu FTX-1 series transceiver, focused on driving an
external antenna tuner (e.g. a mAT-Tuner mAT-30) through a stepped frequency
sweep so it can build up its internal tuning memories on a new antenna, plus
reading back live status (VFO, mode, power, tuner activity) for a GUI.

Command reference: FTX-1 Series CAT Operation Reference Manual (Yaesu, 2508-C),
see refs/FTX-1_CAT_OM_ENG_2508-C.pdf in this project.

Commands used:
  FA<9-digit Hz>;   Set/read MAIN VFO frequency                     (manual p.16)
  AC1,0,3;          Antenna tuner: external, tuning start           (manual p.6)
  AC1,0,0;          Antenna tuner: external, tuning stop / off      (manual p.6)
  RI;               Radio information; P6 = antenna tuner tuning    (manual p.22)
  PC;               Read configured TX power (P1=head, P2=watts)    (manual p.21)
  MD0;              Read MAIN-side operating mode                   (manual p.19)

The FTX1 object is safe to share across threads (e.g. a status poller and a
sweep runner): every command acquires an internal lock for its full
write+reply round trip, so callers never see interleaved responses.
"""
import csv
import re
import threading
from collections import OrderedDict, defaultdict
from pathlib import Path

import serial

# Canonical band display/sweep order. Anything in the TSV not listed here
# (e.g. a future 60m entry) just gets appended after these, sorted by name.
BAND_ORDER = ["160m", "80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]

DEFAULT_LICENSE_ID = "us_general"

BANDPLANS_TSV = Path(__file__).parent / "bandplans.tsv"

_FA_RE = re.compile(r"FA(\d{9});")
_RI_RE = re.compile(r"RI(\d)(\d)(\d)(\d)(\d)(\d)(\d)(\d);")
_PC_RE = re.compile(r"PC(\d)(\d{3});")
_MD_RE = re.compile(r"MD0([0-9A-Fa-f]);")

MODE_NAMES = {
    "0": "-", "1": "LSB", "2": "USB", "3": "CW-U", "4": "FM", "5": "AM",
    "6": "RTTY-L", "7": "CW-L", "8": "DATA-L", "9": "RTTY-U", "A": "DATA-FM",
    "B": "FM-N", "C": "DATA-U", "D": "AM-N", "E": "PSK", "F": "DATA-FM-N",
    "H": "C4FM-DN", "I": "C4FM-VW",
}


EDGE_PAD_HZ = 1000


def frequencies_for(ranges, step_hz):
    """Expand (start_hz, end_hz) ranges into an ascending sweep frequency list.

    Ranges are swept low to high (and sorted first, so mixed band/custom
    selections still come out in one ascending sequence). Within each range,
    the first point is nudged EDGE_PAD_HZ above the lower edge and the last
    point EDGE_PAD_HZ below the upper edge - so the sweep never transmits
    exactly on a hard band boundary - and every point in between lands on a
    clean multiple of step_hz.
    """
    freqs = []
    for start, end in sorted(ranges):
        first = start + EDGE_PAD_HZ
        last = end - EDGE_PAD_HZ
        if last <= first:
            # Too narrow for edge padding plus interior grid - just use the edges.
            for f in sorted({start, end}):
                if f not in freqs:
                    freqs.append(f)
            continue

        points = [first]
        grid = (first // step_hz + 1) * step_hz  # first grid point strictly above `first`
        while grid < last:
            points.append(grid)
            grid += step_hz
        points.append(last)
        freqs.extend(points)
    return freqs


def load_licenses(path=BANDPLANS_TSV):
    """Parse bandplans.tsv into a list of license/country profiles.

    Each row is one legal frequency sub-range for one band under one
    license; a band with mode-restricted segments (e.g. US General's 80m
    CW/data + phone split) simply has multiple rows sharing the same
    license_id and band. The file is user-editable - re-read it fresh on
    every call rather than caching, so edits take effect without a restart.

    Returns a list of dicts:
      {license_id, license_name, country_group,
       bands: {band_name: [(start_hz, end_hz), ...]}}
    sorted with country_group "US" first, then alphabetically.
    """
    licenses = OrderedDict()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for order, row in enumerate(reader):
            lid = row["license_id"]
            if lid not in licenses:
                licenses[lid] = {
                    "license_id": lid,
                    "license_name": row["license_name"],
                    "country_group": row["country_group"],
                    "bands": defaultdict(list),
                    "_order": order,
                }
            start, end = int(row["start_hz"]), int(row["end_hz"])
            licenses[lid]["bands"][row["band"]].append((start, end))

    result = list(licenses.values())
    # Preserve the TSV's own ordering within a group (e.g. Technician before
    # General before Extra) rather than sorting license_id alphabetically.
    result.sort(key=lambda lic: (lic["country_group"] != "US", lic["country_group"], lic["_order"]))
    for lic in result:
        del lic["_order"]

    for lic in result:
        ordered = OrderedDict()
        for band in BAND_ORDER:
            if band in lic["bands"]:
                ordered[band] = sorted(lic["bands"][band])
        for band in sorted(lic["bands"]):
            if band not in ordered:
                ordered[band] = sorted(lic["bands"][band])
        lic["bands"] = ordered

    return result


class FTX1:
    def __init__(self, port, baud=38400, timeout=1.5):
        self._lock = threading.RLock()
        self.ser = serial.Serial(
            port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=timeout
        )

    def close(self):
        with self._lock:
            try:
                self.ser.close()
            except Exception:
                pass

    def _write(self, cmd):
        self.ser.reset_input_buffer()
        self.ser.write(cmd.encode("ascii"))

    def _read_reply(self, timeout=1.0):
        old = self.ser.timeout
        self.ser.timeout = timeout
        try:
            data = self.ser.read_until(b";")
        finally:
            self.ser.timeout = old
        return data.decode("ascii", errors="replace")

    # -- writes (sweep) --------------------------------------------------

    def set_frequency_hz(self, hz):
        with self._lock:
            self._write(f"FA{hz:09d};")

    def tuner_start(self):
        """Equivalent to a 2-second hold of the front-panel [TUNER] button."""
        with self._lock:
            self._write("AC103;")

    def tuner_stop(self):
        with self._lock:
            self._write("AC100;")

    # -- reads (status / sweep completion) --------------------------------

    def tuner_is_tuning(self):
        """True/False, or None if the radio's reply didn't parse as expected."""
        with self._lock:
            self._write("RI;")
            reply = self._read_reply()
        m = _RI_RE.search(reply)
        return m.group(6) == "1" if m else None

    def read_frequency_hz(self):
        with self._lock:
            self._write("FA;")
            reply = self._read_reply()
        m = _FA_RE.search(reply)
        return int(m.group(1)) if m else None

    def read_power_w(self):
        with self._lock:
            self._write("PC;")
            reply = self._read_reply()
        m = _PC_RE.search(reply)
        return int(m.group(2)) if m else None

    def read_mode(self):
        with self._lock:
            self._write("MD0;")
            reply = self._read_reply()
        m = _MD_RE.search(reply)
        return MODE_NAMES.get(m.group(1).upper()) if m else None

    def ping(self):
        """Cheap liveness check - a real radio will answer a frequency read."""
        return self.read_frequency_hz() is not None
