# AGENTS.md — FTX-1 tuner sweep

A local browser app that steps a Yaesu FTX-1's VFO across chosen bands and
triggers an external antenna tuner (a mAT-30) at each stop, so one sweep fills
the tuner's memories for a new antenna.

## Start here

| Read | For |
|---|---|
| `README.md` | What it is, who it is for, features |
| `docs/usage.md` | Running it |
| `docs/band-privileges.md` | How the band plan file works |
| `refs/` | Primary sources: the FTX-1 CAT manual and 47 CFR 97.301, as PDFs |

## Things that cost a lot to rediscover

- **Every sweep step is a real transmission**, and the tool cannot hear the
  band. No code path may key the radio without the pre-flight checklist having
  been ticked, and the stop button must stay reachable. Treat that as a
  requirement, not a disclaimer.
- **The radio cannot know when an external tuner has finished.** The `RI`
  status bit never clears for a third-party tuner, because the trigger line is
  one-way. Do not reintroduce completion polling; the tool holds each frequency
  for a fixed dwell (5 s) and moves on.
- **`AC` set to "external tuner, start tuning" is the front-panel TUNER button
  held for two seconds.** That is the trigger the mAT-30 is wired to.
- **Band data comes from 47 CFR §97.301 itself**, checked into `refs/`, never
  from a summary site. Non-US entries are flagged placeholders built from ITU
  region tables and must stay flagged.
- **Edge padding is deliberate**: the first stop sits 1 kHz above a segment's
  lower edge and the last 1 kHz below its upper edge, so it never transmits on
  a hard boundary.
- **Leave the tuner in circuit** however a sweep ends — finished, stopped, or
  the USB cable pulled. An early version left it bypassed, which is worse than
  not having run.

## Where it stands

Field-tested against a real FTX-1 Optima and mAT-30 on 15 m and 12 m. Both real
bugs were found on the air rather than on the bench. No automated test suite.

## How I work — standing preferences

These are the same in every repository of mine. They are restated in each one
so that any assistant reads them, not only the one configured on my machine.

**Git is mine.** Never run `git commit` or `git push`, in any repository, for
any reason. Reading history is encouraged — `log`, `diff`, `status`, `show` —
and so is telling me when a good commit point has been reached, or drafting a
commit message for me to use. Finish the work, leave it uncommitted, and say
what changed and where.

**Hardware is mine.** Do not build SD-card images, `rsync` to a device, open an
`ssh` session to one, or run anything on a Raspberry Pi or the cyberdeck unless
I ask in that message. Hand me the exact commands to copy and paste — one block
per step, in order — say what each should print, and stop. I will run them and
paste the output back. Local work in the repository needs no such restraint.

**Writing.** No British spellings; US throughout. Design documents are
declarative: no hero's-journey narrative, no second-person "you", and never
state something as fact and then refute it a few lines later. For an article
already published, add a dated update section rather than rewriting the
narrative — the wrong turns are part of why it is worth reading. Do not repeat
a warning I have already acknowledged.

**Images.** Look at any photograph or screenshot before adding it to an
article, a slide deck, or a repository. Phone numbers show up in radio screens
and log captures, coordinates show up in beacon lines and station pages, and
backgrounds show rooms. Say what you found and redact it rather than guess.

**Destructive commands.** `/dev/sdX` stays a placeholder in any flashing or
disk-writing instructions. Never substitute a real device node.

**Amateur radio.** Test traffic uses my own callsign and its SSIDs — never
another operator's call, unless I explicitly ask for one.

**Working style.** I start fresh sessions often rather than carrying one for
weeks, so assume no memory of previous conversations. Everything you need
should be in this file or in the documents it points at.

**Keeping this file true is part of the work.** Anything dated here records
what was true on that date, not what is true now — check it against the
repository before relying on it, and correct it when it is wrong. When a
session has changed how the project works, turned up a gotcha worth the next
session not rediscovering, or outdated something in a "where it stands"
section, propose the edit to this file before the session ends. Do not wait to
be asked, and do not save it for a tidy-up later: the next session starts cold,
and this file is most of what it gets.
