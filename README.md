# FTX-1 Tuner Sweep

A small local web app that steps a Yaesu FTX-1's VFO across chosen amateur
bands and triggers an external antenna tuner (e.g. a mAT-Tuner mAT-30) at
each 10 kHz stop, so the tuner builds up its per-frequency memories on a new
or different antenna.

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

See [docs/usage.md](docs/usage.md) for the physical setup, required radio
menu settings, and a pre-flight checklist before running a real sweep.
