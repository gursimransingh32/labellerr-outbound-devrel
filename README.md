# Labellerr AI: Robotics Outbound & DevRel take-home

Submitted by **Gursimran Singh**

## Summary Card

| Section | What I did | Confidence | Time | Files |
|---|---|---|---|---|
| Company list | 20 companies in 5 segments, checked against 24 disclosed customers/partners (incl. a by-eye check of the logo wall) and 37 brands those customers own; a why-now line per company, ranked by the script | 4/5 | ~50 min | [docs/01_target_list.md](docs/01_target_list.md), [data/targets.csv](data/targets.csv) |
| Contacts | 40 named contacts (technical buyer + exec/intro route per company), each linked to a source and checked on LinkedIn where possible; 3 still marked to confirm | 4/5 | ~30 min | [data/contacts.csv](data/contacts.csv) |
| Strategy note | Channel per segment, why it fits, and a 17-day multi-threaded sequence | 4/5 | ~20 min | [docs/02_strategy_note.md](docs/02_strategy_note.md) |
| 3 outreach messages | Addverb, Apptronik, Generalist AI; each under 150 words and built on a company-specific signal | 4/5 | ~25 min | [docs/03_outreach_messages.md](docs/03_outreach_messages.md) |
| Bonus: follow-ups | 3-message no-reply sequence for the Apptronik email | 4/5 | ~10 min | [docs/04_followup_sequence.md](docs/04_followup_sequence.md) |
| Automation | Python (stdlib only): live do-not-contact check with subsidiary matching, explainable lead scoring, first-draft generator; 13 unit tests | 4/5 | ~35 min | [src/outbound.py](src/outbound.py), [tests/](tests/), [output/](output/) |
| Reflections | Answers to the two closing questions | - | ~10 min | [docs/05_reflections.md](docs/05_reflections.md) |
| **Total** | | | **~180 min** | |

> Confidential: prepared for Labellerr AI's screening round only.

## Run it

```bash
bash setup.sh     # checks Python 3.8+, runs the unit tests (no pip installs)
bash run.sh       # refresh Labellerr pages -> DNC check -> score -> drafts
bash run.sh --offline --as-of 2026-09-28   # reproducible run without network
```

Outputs land in `output/`: `dnc_report.csv`, `ranked_leads.csv/.md`, `drafts.md`, `run_log.txt`.

## Repo layout

```
data/targets.csv        20 target companies: signal, data needs, hook, why-now, sources
data/contacts.csv       40 contacts with role, persona, verification status and source
data/dnc_snapshot.csv   24 disclosed Labellerr customers/partners + 37 brands they own, with sources
src/outbound.py         the automation (refresh, check, score, draft)
tests/                  13 unit tests (python3 -m unittest)
docs/                   target list, strategy note, messages, follow-ups, reflections
output/                 sample output from the run on 2026-09-27
```

## What the automation does

- **1. Refresh:** Downloads Labellerr's public case-study and robotics pages, strips the HTML, and caches the text and every /case-study/ link. If the network is down it falls back to the cache, then to the committed snapshot.
- **2. Check:** Compares each target with the do-not-contact list: 24 disclosed customers/partners plus 37 brands they own. An exact or near-exact name match to a customer (difflib similarity of 0.88 or more, after removing suffixes like Inc.) is BLOCK. A shared distinctive word (e.g. 'toyota' in Toyota Research Institute) is REVIEW, which catches subsidiaries. A match to a customer-owned brand (e.g. Zenseact, owned by Volvo Cars) is REVIEW. Any mention on the live pages is REVIEW, which catches customers added after the snapshot.
- **3. Score:** Ranks leads out of 100 with weights kept in one place: recency of the signal (25), signal type such as funding or explicit data-infrastructure spend (20), data-type fit such as egocentric, teleop or manipulation (20), winnability by company size (15), a matching Labellerr case study (10), warm path (5), India link (5). Every score prints its breakdown so the ranking can be argued with.
- **4. Draft:** Builds a first-draft opener per contact from the row's hook, pain and proof point, with persona-specific wording (technical, exec, intro). It flags drafts over 150 words, companies pending DNC review, and contacts not yet confirmed. These drafts are a starting point; the three final messages were rewritten by hand.

**Design choices**

- Standard library only, so bash setup.sh and bash run.sh work on a clean Mac or Linux machine with just Python 3.8+ and bash.
- The data lives in CSVs a salesperson can edit; the logic lives in one readable file.
- It fails safe: no network means cached pages plus the snapshot, never a silent 'all clear'.
- 13 unit tests cover the risky parts: suffix matching (Inc., AB), subsidiary and owned-brand detection, logo-only customers, generic-word false positives, a check of the real list, scoring bounds and the draft word limit.

## Ranked output (sample run)

| # | Company | Tier | Score | Breakdown |
|---|---|---|---|---|
| 1 | Addverb | A | 90 | recency=25 signal=15 data_fit=18 winnability=12 proof_point=10 warm_path=5 india=5 |
| 2 | Apptronik | A | 87 | recency=25 signal=20 data_fit=20 winnability=12 proof_point=10 warm_path=0 india=0 |
| 3 | Agility Robotics | A | 77 | recency=25 signal=15 data_fit=15 winnability=12 proof_point=10 warm_path=0 india=0 |
| 4 | Skild AI | A | 77 | recency=20 signal=15 data_fit=18 winnability=4 proof_point=10 warm_path=5 india=5 |
| 5 | CynLr | A | 75 | recency=20 signal=10 data_fit=15 winnability=15 proof_point=10 warm_path=0 india=5 |
| 6 | Mind Robotics | A | 75 | recency=20 signal=18 data_fit=15 winnability=12 proof_point=10 warm_path=0 india=0 |
| 7 | NEURA Robotics | A | 75 | recency=20 signal=20 data_fit=18 winnability=12 proof_point=0 warm_path=5 india=0 |
| 8 | Perceptyne | A | 75 | recency=12 signal=15 data_fit=18 winnability=15 proof_point=10 warm_path=0 india=5 |
| 9 | 1X | B | 70 | recency=20 signal=18 data_fit=20 winnability=12 proof_point=0 warm_path=0 india=0 |
| 10 | Generalist AI | B | 70 | recency=20 signal=18 data_fit=20 winnability=12 proof_point=0 warm_path=0 india=0 |
| 11 | AIM Intelligent Machines | B | 66 | recency=12 signal=15 data_fit=9 winnability=15 proof_point=10 warm_path=5 india=0 |
| 12 | Ati Motors | B | 62 | recency=2 signal=15 data_fit=15 winnability=15 proof_point=10 warm_path=0 india=5 |
| 13 | Sunday | B | 60 | recency=12 signal=18 data_fit=18 winnability=12 proof_point=0 warm_path=0 india=0 |
| 14 | Genesis AI | C | 59 | recency=20 signal=10 data_fit=17 winnability=12 proof_point=0 warm_path=0 india=0 |
| 15 | Physical Intelligence | C | 59 | recency=20 signal=15 data_fit=20 winnability=4 proof_point=0 warm_path=0 india=0 |
| 16 | Rhoda AI | C | 58 | recency=12 signal=15 data_fit=19 winnability=12 proof_point=0 warm_path=0 india=0 |
| 17 | Carbon Robotics | C | 56 | recency=12 signal=15 data_fit=7 winnability=12 proof_point=10 warm_path=0 india=0 |
| 18 | Symbotic | C | 50 | recency=12 signal=8 data_fit=9 winnability=6 proof_point=10 warm_path=5 india=0 |
| 19 | Dyna Robotics | C | 48 | recency=6 signal=13 data_fit=17 winnability=12 proof_point=0 warm_path=0 india=0 |
| 20 | Mobileye (Mentee Robotics) | C | 41 | recency=12 signal=8 data_fit=15 winnability=6 proof_point=0 warm_path=0 india=0 |

## Reflections

**What would you improve about your submission if you had two more hours?**

I would add a third contact at each account, a head of robot learning or data operations, because many of my contacts are founders who may forward vendor email, and Mind Robotics has no public data lead at all. Next, I would replace the hand-entered signal dates with an RSS pull from Robotics 24/7 and TechCrunch Robotics so the scores refresh themselves. I would also add a reachability factor, because the ranking currently cannot tell that Rivian's CEO is harder to reach than the CTO of a 50-person startup. Finally, I would pull customers' brand families automatically (for example from Wikidata's parent-organization field) instead of maintaining that list by hand.

**What's one thing about this task you didn't already know how to do, and how did you figure it out?**

I did not know how to prove that a company is not a customer, because 'not on the case-study page' is not the same as 'not a customer'. I layered sources: the case-study page, the logo wall (its alt text is broken, so I read it by eye and found MIT and Kapsys, which appear nowhere else), Labellerr's LinkedIn tagline, which named Toyota AI and UC Davis, and third-party listings; an unnamed testimonial on its homepage turned out to be an ex-Oishii engineer now at AIM, which became a warm path. The Toyota finding showed me that exact name matching is not enough, so I read the Python difflib documentation, added a distinctive-word check for subsidiaries, and mapped each customer's brand family (Volvo Cars owns Zenseact, Coupang owns Farfetch, Oishii bought Tortuga AgTech) so those brands are held for review. I used an AI assistant, which the brief allows, to speed up research and first-draft code, and every company and contact in the list links to its source so it can be checked.
