# Setup and usage

## What this does

Walks the FTX-1's VFO across one or more amateur bands in fixed frequency
steps (10 kHz by default), and at each stop triggers the external antenna
tuner (e.g. a mAT-Tuner mAT-30) to run its auto-tune cycle. Auto tuners like
the mAT-30 store a memory per frequency, so after a sweep the tuner should be
able to recall a near-instant match anywhere across the swept range, on
whatever antenna is currently connected.

## Physical setup

1. Connect the FTX-1 to your computer over USB-C. This exposes two virtual
   COM ports: an Enhanced COM Port (CAT-1) and a Standard COM Port (CAT-2).
   This app uses **CAT-1**. On Windows this requires the Silicon Labs CP210x
   driver from the Yaesu site; on Linux it should enumerate as
   `/dev/ttyUSB0`/`/dev/ttyUSB1` (cp210x kernel driver) without extra setup.
2. Connect the mAT-30 to the FTX-1's **TUNER/LINEAR** jack using the mAT-CY
   control cable, and connect your antenna to the mAT-30's output.

## Radio menu settings (required)

- `OPERATION SETTING` &rarr; `GENERAL` &rarr; **TUN/LIN PORT SELECT** = `EXT-TUNER`
  (not `LINEAR`, `CAT-3`, or `GPO` — those repurpose the same jack for other
  things and the mAT-30 won't respond)
- `OPERATION SETTING` &rarr; `GENERAL` &rarr; **TUNER SELECT** = `EXT`
  (not `INT`, `INT(FAST)`, or `ATAS`)
- `OPERATION SETTING` &rarr; `GENERAL` &rarr; **CAT-1 RATE**: factory default
  is 38400 bps, which is what this app defaults to. If you've changed it,
  match the baud rate field in the UI to whatever the radio is set to.

## Running it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000. The page is fully usable without a radio
attached - you can browse bands and sweep settings freely. A dot next to
"Connection" shows whether a radio is actually connected.

- Pick the serial port (the dropdown lists detected ports; pick the CAT-1 /
  Enhanced COM Port one, not CAT-2) and hit **Connect**. Once connected, the
  panel shows live VFO frequency, mode, configured power, and whether the
  tuner is actively cycling - useful for confirming CAT is really working
  before you trust it to run a sweep.
- Pick your license class from the dropdown (US options are listed first;
  US General is the default). The band checkboxes below it update to show
  exactly what that license is allowed to use on each band, including any
  CW/data-vs-phone segment split - check a band and every listed segment for
  it gets swept. See [band-privileges.md](band-privileges.md) for where this
  data comes from and which entries are exact vs. approximate.
- Enter custom Hz ranges (`lo-hi`, comma-separated) if you want a narrower
  slice than what a band checkbox gives you.
- Check the pre-flight checklist box once you've actually confirmed those
  items, then hit **Start sweep** (only enabled once connected).
- **Stop** finishes the in-progress step, leaves the tuner enabled (not
  bypassed), and halts.
- **Disconnect** closes the serial port; the sweep won't run without a live
  connection.

## Before your first real sweep

This was built directly from the FTX-1 CAT Operation Reference Manual
(`refs/FTX-1_CAT_OM_ENG_2508-C.pdf`) and has been field-tested against a real
FTX-1 Optima and mAT-30 on 15m and 12m. Still, before sweeping a whole band
unattended on gear you haven't tried this with, test with a single narrow
custom range (e.g. `7100000-7110000`) and confirm the mAT-30 actually cycles
during the dwell. In practice, expect most steps to log `dwell` rather than
`ok` - the FTX-1 can't reliably tell you when an *external* tuner has
finished, so `dwell` (it held the frequency for the full dwell time without
an early confirmation) is the normal outcome, not a failure. Set the dwell
time in Sweep settings to comfortably cover how long your mAT-30 actually
takes to tune.

## Safety notes

- Every step is a real transmission. Use the **minimum power that still
  gets a reliable tune - 5W or less**. There's no benefit to tuning at
  higher power, and it needlessly increases both interference potential and
  stress on the tuner's relays across a whole sweep. Pick the license class
  that actually matches what you hold - the US entries are exact, but the
  Canada/Europe/Japan/Central & South America entries are approximate
  reference allocations, not verified per-class tables (see
  [band-privileges.md](band-privileges.md)). If in doubt, use a custom range
  you've confirmed yourself rather than trusting a `_ref` entry.
- A full multi-band sweep at 10 kHz steps takes a while (tens of steps per
  band, several seconds each with tuning). Don't leave it running somewhere
  you can't hear it or physically stop it if something looks wrong.
- If you hit **Stop**, the app still leaves the tuner enabled (not
  bypassed) and closes the serial port in the background, but nothing
  replaces being able to reach the radio's power switch.
- **Be a good neighbor on the band.** Only run an automated sweep when the
  segment you're about to cross looks dead or nearly so - listen first.
  If you see or hear activity that you're about to tune across (a QSO, a
  net, a beacon), hit **Stop** immediately rather than sweeping through it.
  A sweep has no way to know a frequency is in use before it keys up there.

## Project layout

- `app.py` — Flask app: web routes, connection state, background sweep and
  status-poller threads
- `ftx1_cat.py` — FTX-1 CAT protocol (serial framing, `FA`/`AC`/`RI`/`PC`/`MD`
  commands) and the `bandplans.tsv` loader
- `bandplans.tsv` — license classes and their legal frequency ranges, user
  editable (see [band-privileges.md](band-privileges.md))
- `templates/index.html` — the browser UI (self-contained, no build step)
- `refs/` — source documentation (Yaesu CAT manual, FCC 47 CFR 97.301, CEPT
  Novice recommendation)
