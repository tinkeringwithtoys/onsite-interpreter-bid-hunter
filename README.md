# onsite-interpreter-bid-hunter

Scheduled RFQ/tender hunter for a **Tunisian** interpreting provider working
**AR↔FR** and **AR↔EN**, based in Tunis, accepting **both onsite and remote/RSI**.

Runs on GitHub Actions. No laptop, no server, no 24/7 machine.

---

## v4 · The entity is Tunisian, not EU

The Portuguese registration is **not done**. v3 assumed it was, and v3 therefore
ranked the sources wrongly. This version fixes the ranking.

**The EU profile is not deleted.** It sits dormant in
`config.yaml` → `profile.future_profiles.eu_portugal`, and comes back with a
single line the day Portugal completes:

```yaml
profile:
  active_profile: eu_portugal   # currently: tunisian
```

That block also records what reactivating it *unlocks*, so nothing learned in v3
was lost — it was parked.

### Why this reorders everything

Three facts, verified rather than assumed, because getting this wrong costs
weeks of unpaid bid-writing:

1. **Tunisia is not a party to the WTO Government Procurement Agreement.** The
   WTO's own notification portal records Tunisia as *"Not applicable, not a
   Party"*. It isn't on the observer list either.
2. **Under the CJEU's Kolin / Qingdao line of cases**, operators from third
   countries that are neither GPA signatories nor covered by a procurement
   agreement with the EU cannot rely on the Procurement Directive — including
   the right to equal treatment and the right to challenge an award.
3. **The Commission's 2025 Q&A goes further.** A contracting authority may say
   nothing about third-country participation in the notice and still accept or
   reject such a bid *at any moment during the procurement process*.

Point 3 is the one that matters operationally. It means a Tunisian entity can
write a complete bid, submit it, and be dropped at any stage — no notice, no
reason, no appeal. **The risk isn't losing a tender. It's spending three weeks
on a submission with no enforceable right to an outcome.**

And this exposure reaches **named subcontractors and consortium members**, not
just the lead bidder. So "just subcontract to the winner" is *not* the clean
workaround it sounds like — see below for the route that is.

### What this does NOT mean

It does not mean the EU sources get deleted. All 21 remain. They're **re-labelled**
so an alert tells you which action is actually available:

| Label | Meaning |
|---|---|
| `bid_directly` | Submit as lead bidder. No nationality barrier. |
| `domestic` | Home market, full access. |
| `commercial_only` | Ordinary B2B contract. Procurement law doesn't apply. |
| `watch_and_partner` | Don't write a solo bid. Intelligence + a prime to approach. |

### The route that does work

When you contact a framework winner, **ask to join their interpreter roster — do
not ask to be a named subcontractor.** A prime engaging you as an individual
freelance interpreter is buying a service, not naming a corporate subcontractor
in its bid. Same work, materially less legal friction, and a much faster yes.

---

## Where the work actually is (v4 order)

### 0. UN system ← now your strongest lane

This moved from third to first, and not as a consolation prize. UN procurement
has **no nationality restriction**, and UNGM's own figures say **85.9% of its
suppliers are from developing countries**. Tunisian registration is
neutral-to-positive here — never a barrier.

Arabic is also one of the six official UN languages, which is a structurally
better fit than the EU, where Arabic isn't official at all.

**Do this week:** register on UNGM at Basic level. It's free and it gates
everything. Note the ceiling — Basic covers contracts up to USD 150,000; Level 2
(over USD 500,000) needs a certificate of incorporation, **three years minimum in
business**, three reference letters and three years of audited financials. Check
the company's age before promising capacity on a large lot.

### 0b. African Union / AfDB ← also promoted

Tunisia is an **AU member state**. AU bid documents ask for company registration,
a valid business licence and a tax certificate — all of which a Tunisian entity
holds natively. The AfDB was headquartered in Tunis for over a decade; local
presence is an advantage there, not a flag.

### 0c. Private-sector work ← completely unaffected

Contracts with EU language service providers, agencies and RSI platforms are
**ordinary commercial services exports**. Public procurement law does not apply
at all. None of the third-country analysis above touches this channel, which is
why it's now a primary lane rather than an afterthought.

Invoicing note: you invoice EU businesses **without VAT** under the reverse
charge — the client accounts for it in its own country. Open a *compte
professionnel en devises* **before** the first EUR invoice, not after; a Tunisian
resident company with export earnings may credit 100% of them to it. The dinar is
convertible for current-account transactions but is not fully convertible.

### 1. EU asylum / migration / border interpreting ← still the biggest market, now `watch_and_partner`

Everything below about *why this market is attractive* remains true. What changed
is your **role** in it: intelligence and partner-hunting, not solo bidding — until
Portugal completes.

This is the largest Arabic-interpreting buyer in Europe, and it has four
properties that make it unusually winnable:

| Property | Why it helps you |
|---|---|
| Procured by public tender | Visible in TED, so the API already covers it |
| Lotted **by language family** | Arabic gets its own lot — you don't compete with Polish providers |
| Awarded to **multiple vendors in cascade** | You don't have to beat everyone, just place |
| Includes **telephone / remote** lots | Zero travel cost — the flight-and-hotel problem disappears |

Confirmed examples:

- **Frontex** `FRONTEX/2025/OP/0036` — Interpretation and Cultural Mediation
  Services, ~€90M over 48 months, **7 geographic lots**. An earlier Frontex
  interpreting framework (~€25M) was awarded to **six** vendors in cascade.
- **EUAA** `EUAA/2022/052` — Interpretation and/or Cultural Mediation Services,
  multiple framework contracts across lots 1–5. Its predecessor `EASO/2020/820`
  explicitly covered **remote interpretation**, inside and outside Malta.
- **OFPRA (France)** — an interpreting framework worth up to ~€42M; a later
  procedure covered *interprétariat **téléphonique*** under CPV 79540000 and was
  lotted by language family, with **LOT-0001 = "Afrique, Maghreb, Proche et
  Moyen Orient"**. That lot is your lot.
- **OFII (France)**, **BAMF (Germany)**, plus recurring re-tenders from
  Bulgaria's refugee agency, Austria's BBU, Slovakia and Luxembourg.

### 2. UN system

Arabic is **one of the six official UN languages** — and the Arabic booth works
**both from and into** Arabic, which matches your bidirectional claim exactly.
Travel and daily allowance are covered *by agreement*, not by negotiation.

The roster route is the **Competitive Examination for Language Positions**:
Arabic as main language, fluency in English **or** French as an active language,
and a first-level university degree. The exam is run **remotely** — you don't
travel to sit it.

### 3. African Union / AfDB

Arabic is an AU **working language** and Tunisia is a member state. The AU runs
explicit freelance-roster expansion calls for AR/EN/FR/PT interpreters.

### 4. Award-notice mining ← the fastest realistic path to cash

An award notice is **not** a missed deadline. It's a named company that just won
a four-year Arabic interpreting framework and now has to staff it. They need
AR↔FR and AR↔EN capacity and they don't want to recruit from zero.

This stream outputs a **contact list**, not a bid. Different pipeline, different
email section.

---

## Correction to my earlier advice

I previously ranked **EU freelance interpreter accreditation (ACI)** as a top
channel for you. **With AR↔FR / AR↔EN that was wrong**, and you should know why:

- The interinstitutional accreditation test is organised around **EU official
  languages**. Arabic is not one.
- EU guidance does state there's no nationality requirement and that "all
  languages may be considered", with a **limited** need for Arabic, Chinese and
  Japanese.

So the door isn't shut — it's narrow and infrequent. It's now a **quarterly
calendar check**, not a scraper target. Check
`europa.eu/interpretation/doc/aci_test_calendar.pdf` for an Arabic cycle.

## Correction to your earlier assumptions

- **Portugal is redundant as a separate source.** It's an EU member, so its
  above-threshold contracts are already 100% in TED. `BASE.gov.pt` adds only
  below-threshold work.
- **The Gulf will underperform for you, and for a reason you may not expect.**
  Beyond the classification/local-partner barriers, **Arabic isn't scarce there.**
  In Europe you're the scarce resource; in Riyadh you're competing against
  locals. Kept at tier P4 — cheap to monitor, low expected yield.

---

## Two economics lanes, two floors

Because you accept remote work, one filter is no longer enough.

```
LANE A  remote / RSI / telephone     no flight, no hotel, no visa
        net floor  €120/day-equiv    ← your volume lane

LANE B  onsite                       travel must be covered or netted out
        net floor  €350/day
        if travel + DSA is covered → ignore the floor entirely
```

**Watch the unit of account.** Asylum telephone interpreting is usually billed
per **minute** or per **connected call**, not per day. Never compare that number
to a conference day rate. The scorer extracts `unit_of_account` before it
estimates value.

---

## Date logic — three questions, three fields

The most common way these pipelines break is by collapsing these into one.

```
ELIGIBILITY   deadline >= today              is it open at all?
ALERTING      publication_date >= now - 24h   is it new since I last looked?
URGENCY       days_until_deadline             sort by this — NEVER filter by it
```

Filtering by urgency throws away the 60-day framework contracts, which are
exactly the ones worth preparing a real bid for.

Urgency bands: `sprint` <5 days · `sweet_spot` 5–30 · `park` >30.

---

## Vocabulary trap (this one costs real money)

In French, the asylum market and the conference market use **different words**:

- **`interprétariat`** — asylum, social, telephone, community
- **`interprétation`** — conference, simultaneous

Query only the second and you systematically miss the largest Arabic-interpreting
buyer in France. Same in English: the asylum market says **"cultural mediation"**,
which is bundled into the Frontex and EUAA tender titles.

All variants are in `config.yaml` under `queries.keywords`.

---

## Yes, it runs 24/7 — and I under-scheduled it earlier

The infrastructure genuinely runs unattended. GitHub's servers execute the cron
with your laptop shut and your internet off. That part was never in doubt.

But I throttled **everything** to 3×/weekday to protect the minute budget, and
that was over-cautious. **The expensive thing is Playwright, not polling.** Split
the lanes by cost and the cheap lane runs hourly, 24/7, and the month still ends
at ~49% of the free allowance.

| Lane | Touches | Cadence | Runs/mo | Billed min/mo |
|---|---|---|---|---|
| `fast` | TED + EU F&T JSON APIs — no browser | **Hourly, 24/7** | 730 | 730 |
| `standard` | HTTP scrapes + deadline watch | 3× daily, every day | 91 | 182 |
| `heavy` | Playwright/Chromium (TUNEPS only) | 1× daily, weekdays | 22 | 66 |
| | | **TOTAL** | **843** | **978 / 2,000** |

GitHub rounds every job **up** to the nearest minute, so a 20-second run bills a
full minute. That rounding is the entire reason the fast lane must stay
browser-free — hourly Playwright would cost 1,460–2,190 min/month on its own and
blow the free tier, which is the mistake in the original blueprint.

Want it cheaper? Change the fast cron to `0 */2 * * *`. Nothing in public
procurement is minute-sensitive, so you lose nothing real.

Keep the repo **private**. A public repo gets unlimited Actions minutes, but it
also publishes your entire target list and strategy.

---

## The hole that 24/7 polling does NOT fix

This is the thing worth knowing, because more frequency would never have found it.

The scraper answers **"what is NEW?"**. Nothing answered **"what is about to
CLOSE?"**

A 45-day framework contract is *correctly* parked the day you first see it — you
have time, no action needed. But it's now in `seen.json`, so the new-notice
pipeline **deduplicates it out forever**. Six weeks later the deadline passes and
you never hear about it again. Running hourly instead of daily changes nothing:
the item was already seen on run one.

`deadline_watch.py` closes it. Reminders at **T-14 / T-7 / T-3 / T-1**, each band
firing exactly once — four emails over six weeks, not forty.

One subtlety it handles: if an item is first seen with **5 days left**, bands 14
and 7 are both technically "entered". It reports the *tightest sensible* band (7)
and burns band 14 so it can never fire afterwards. Announcing "14 days left" when
5 remain is worse than saying nothing.

It also flags per item:

- `onsite abroad with 12d left — check visa lead time` (ties to your Schengen runway)
- `travel + accommodation covered` — the trump card
- `remote — no travel constraint`

And on expiry it tells you **whether you actually bid**, so you can see what you
let slip instead of it vanishing quietly.

Verified by running it, not by asserting it:

```
SELF-TEST PASSED  (10/10 checks)

DEADLINES APPROACHING
  T-3d   [place_fr]  OFPRA interpretariat telephonique
           closes 2026-08-10 · telephone
           ! remote - no travel constraint
  T-12d  [frontex]   Frontex AR interpretation LOT-6
           closes 2026-08-19 · onsite
           ! onsite abroad with 12d left - check visa lead time

CLOSED SINCE LAST RUN
  stale one  (NO BID SUBMITTED)
```

Re-run immediately after: `No deadline milestones due today.` — idempotent, so it
won't spam you.

---

## Two more failure modes now handled

**Silence is ambiguous.** A broken workflow and "no new opportunities" look
*identical* in your inbox — and the broken one looks calmer. The standard lane now
has an `if: failure()` step that emails you when the run dies, so quiet means
quiet, not dead.

**Scheduled workflows self-destruct.** GitHub disables cron after 60 days of
repository inactivity. I am *not* assuming bot commits reset that timer — treat
that as unproven. The heavy lane writes `.keepalive/last_run` so the repo is never
idle. If schedules ever stop firing anyway, trigger any workflow manually via
`workflow_dispatch` to revive them.

Also: cron on the free tier can lag 5–20 minutes. Irrelevant here — no deadline in
public procurement is minute-sensitive.

---

## Run the validator before any scraper exists

```bash
python3 validate_sources.py --json local_report.json
```

Zero dependencies, standard library only. It answers the three questions that
decide the architecture:

1. Which sources respond at all?
2. Which need a real browser vs. plain HTTP?
3. **Which ones block GitHub Actions' datacenter IPs?**

It also probes TED for a working expert-query syntax — CPV filter, 24h date
window, **Arabic narrowing**, and the **award-notice filter** — instead of me
hard-coding field names I haven't executed.

### Run it twice. This is the important part.

| Run | Where | Proves |
|---|---|---|
| a | your laptop in Tunis | the source works |
| b | GitHub Actions (`validate.yml`) | the source works **from a runner** |

Any source that passes (a) and fails (b) is **IP-blocked**. GitHub runners use
Azure datacenter ranges, which procurement sites behind Cloudflare and DataDome
routinely challenge. No amount of code fixes that — you'd need a proxy or a
different runner. Learning this on day one instead of week three is the entire
point of running the validator first.

Send me both reports and I'll lock the queries against verified behaviour.

---

## Honest status of what's in here

| Claim | Confidence |
|---|---|
| TED search needs **no** authentication | **Verified in official docs.** EU Login/API keys are for eNotices2 *submission* only |
| CPV 79540000 = Interpretation services | **Verified**, and confirmed live in a real OFPRA notice |
| Frontex/EUAA/OFPRA buy Arabic interpreting by tender | **Verified** from notices and award records |
| Arabic is an official UN language, AR booth does retour | **Verified** from UN DGACM |
| Arabic is *not* an EU official language; need is "limited" | **Verified** from EU guidance |
| EU F&T Portal HTML is JS-rendered, API required | **Verified** |
| Exact TED expert-query **field names** | **UNVERIFIED.** My sandbox has no outbound network — the live call returned HTTP 000. This is why the validator probes five syntaxes instead of trusting one |
| Visa lead times in `config.yaml` | **Placeholders.** Marked TODO. Do not trust |

When the validator reported `0 reachable / 15 need attention`, that was the
sandbox having no network — **not** the sources being down.

---

## Still needed from you

**Which EU member state is the company registered in?** It's now the highest-value
unknown, because it decides three things:

1. Which national below-threshold portal to poll (less contested than TED)
2. Whether you can hold **sworn / court-certified** status — a hard requirement
   in many justice-sector lots
3. Which Frontex/asylum **country-cluster lot** is your natural home bid

Also: your **VAT number**, required on most EU tender submissions.

---

## Security — do this before anything else

The `env.txt` you shared contains **live credentials in plaintext**. Rotate all
three now:

- GitHub personal access token → `github.com/settings/tokens`
- Agnes AI API key → your Agnes dashboard
- Gmail app password → `myaccount.google.com/apppasswords`

Then store them as **GitHub Actions Secrets**, never in the repo.

Two defects in that file, while we're here:

```
SMTP_FROM=your-address@gmail.comALERT_EMAIL=aladinsliti@gmail.com
```

Two variables on one line, so `SMTP_FROM` parses as the whole string and
`ALERT_EMAIL` is **undefined**. `SMTP_FROM` is also still the placeholder. And
`appname=SMTP_PASSWORD` isn't a real variable.

The GitHub PAT is unnecessary — `GITHUB_TOKEN` with `permissions: contents: write`
is enough for the workflow to commit its own state.

---

## Files

```
config.yaml                      all sources, tiers, queries, economics, scoring,
                                 lane cadences, deadline-watch rules
validate_sources.py              zero-dependency source probe — RUN THIS FIRST
deadline_watch.py                T-14/7/3/1 reminders · 10/10 self-tests passing
README.md                        this file

.github/workflows/
  fast.yml                       JSON APIs · hourly · 24/7          ← the always-on lane
  standard.yml                   HTTP scrapes + deadline watch · 3× daily
  heavy.yml                      Playwright · daily weekdays · keepalive
  validate.yml                   manual source probe on a runner
```

Every workflow carries the fixes from the original blueprint: `actions/setup-python@v5`
(not `actions/actions-setup-python`), `python-version` (not `python-with-version`),
explicit `timeout-minutes` (the default is **360**), a `concurrency` group,
`git pull --rebase` with retry before push, and **no `|| true` on the push** — a
failed push must show a red X, not vanish.

### Not built yet

`scraper.py` itself. The workflows call it with `--tier fast|standard|heavy`. I'm
holding it until your validator report comes back, because writing adapters
against unverified endpoints and unverified TED field names is how you get code
that looks right and silently returns nothing.

Adding a source means adding a block to `config.yaml` — never editing scraper
code. That's the "don't overfit to one site" requirement, enforced structurally.
