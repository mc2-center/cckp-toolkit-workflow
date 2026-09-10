# Analysis decisions

Why the analyses are specified the way they are, and what each one cannot establish.

Module docstrings say what a script reads, writes and computes. The reasoning behind a design,
the alternatives rejected, and the limitations a reader should hold against a result live here,
so a docstring stays the length a docstring should be and this record stays in one place where
it can be read end to end. Each section is linked from the docstring of the script it governs.

## Fork accrual as the adoption proxy

The cross-sectional models say practices and adoption coincide, not which comes first. Testing
precedence needs an adoption measure with timestamps, and GitHub does not expose historical star
counts. The forks endpoint returns a `created_at` per fork, so a cumulative series can be
reconstructed for any repository, which makes fork accrual the only time-resolved adoption proxy
available at cohort scale.

Forks are a narrower signal than stars: they count people who copied the code, not people who
bookmarked it. Every result resting on them should be read as being about that narrower
behaviour.

## Matched difference-in-differences

Governs `modeling/matched_did_practice_forks.py`.

### Why the within-repository placebo was replaced

The earlier event study compared each repository's fork rate before and after its license
addition, using a random date in the same repository as a placebo. That design does not support
the conclusion drawn from it, for two reasons found on inspection.

First, the placebo dates sit at a different point in the lifecycle. A date drawn uniformly from a
repository's history lands, on average, mid-life, whereas licenses are added early: the treated
windows open at a mean 0.15 forks per month against the placebo windows' 0.34.

Second, and because of that gap, regression to the mean pushes the two series in opposite
directions. A window opening at a low rate can mostly only rise, one opening at a high rate can
mostly only fall, so part of the reported real-versus-placebo difference is produced by the
baseline mismatch rather than by the license. The same artifact accounts for the finding that 62%
of repositories with no prior forks accelerated afterward: 59% of them also do so after a random
date.

### What replaced it

Control repositories that never adopted the practice, matched on the two quantities that broke
the placebo:

- age at the event date, so treated and control windows sit at the same lifecycle stage
- fork rate in the pre-period, so both sides face the same regression to the mean

Matching on age has a second benefit. A repository younger than twelve months at its event has a
pre-window that extends before its first commit, and rates there are computed over the months
actually observed. Because a treated repository is matched to controls of similar age, both sides
lose the same months, so the truncation cancels instead of biasing the contrast.

### The estimand

The difference in differences: for each treated repository, the change in its fork rate across
the event minus the mean change in its matched controls over the same calendar window. Under the
identifying assumption that matched controls track what the treated repositories would have done
without the practice, a positive value is the effect of adopting it. The pre-event months of the
difference curve are a direct test of that assumption; they should be flat.

### Limitations

- Controls come from repositories failing the practice's check at assessment, so they are never
  treated rather than not-yet treated. Treated repositories are still selected on having
  eventually adopted, which matching cannot fix and which the Limitations section should state.
- Repositories tend to add several artifacts in one housekeeping push, so each estimate is the
  effect of adopting that practice together with whatever arrived alongside it, not of the
  artifact in isolation. The per-practice overlap in co-adoption dates is reported so the extent
  of that bundling is visible.

## Which practices can be dated

A practice qualifies for the design above only if adoption is a dated act recoverable from git
history. Six are: a test suite, common documentation, contributing guidelines, a code of conduct,
a license, and citability.

Three of the Toolkit's checks are not, and their absence is a real limit on the design rather
than an omission:

| Check | Why it cannot be dated |
|---|---|
| `repo_default_branch_not_master` | Renaming a branch leaves no commit, and the GitHub API exposes no rename history, so there is no date to anchor a window on |
| `almanack_score` | A composite over many checks, not a single act, so there is no moment of adoption |
| `repo_includes_readme` | Present at creation for 97% of the cohort, leaving almost no adopters to observe |

JOSS compliance is the strongest feature in the sustainability model and is likewise a composite
with no moment of adoption, but unlike the Almanack score it decomposes into acts that can be
dated. Four of its five criteria reduce to file presence, and this design dates the practices
behind all four: Tests, which is the largest of the five once scored from static evidence;
Installation Instructions and Example Usage, both decided by common documentation; and Community
Guidelines, decided by the contributing file and the code of conduct. Only Statement of Need is
out of reach, being README presence. So the cross-practice figure is also a decomposition of JOSS
compliance, and it is ordered by how much of the variance in the JOSS score each criterion
accounts for.

## The reverse direction

Governs `modeling/reverse_direction_adoption.py`.

The matched difference-in-differences found that fork accrual speeds up after a practice is
adopted for all six datable practices, but also that the treated repositories were already
pulling ahead of their controls before adopting in four of the six. That pre-existing trend is
reported there as a caveat. It is also a measurement of something in its own right.

The question here is the mirror image: given a repository that has not yet adopted a practice,
does a recent burst of forking predict that it adopts in the following months? If it does about
as strongly as adoption predicts forking, the honest reading of both results together is that
practices and attention co-evolve and no directional claim survives. If the forward direction is
much the stronger, the precedence claim is quantified against its main rival rather than merely
defended against it. Either outcome is reportable; the position where only one direction has been
measured is not.

### Design

A discrete-time hazard model on repository-months. For every repository with datable fork
history, each month of its life is one row, and the row is at risk if the repository had not yet
adopted the practice at the start of that month. Repositories that eventually adopt contribute
months up to and including the month they adopt, which carries the event. Repositories failing
the check at assessment never adopt and are censored at their last fully observed month, so they
are never-adopters rather than not-yet adopters, matching the control pool of the forward
analysis.

The predictor is built strictly from months before the row's own month, so no row can see its own
outcome:

| Term | Definition |
|---|---|
| `recent` | Forks in the three months immediately before this month |
| `baseline` | Mean monthly forks over the twelve months before those three |
| `accel` | log2 of the recent rate over the baseline rate, in doublings |

`accel` is the quantity of interest: forking above the repository's own recent norm. `baseline`
enters separately as a covariate, so the coefficient on `accel` is the effect of accelerating
rather than the effect of being a busy repository. Cumulative forks to date and age enter for the
same reason, and calendar year absorbs the cohort-wide growth in both forking and in the
prevalence of these practices, which would otherwise correlate the two by itself.

The reported effect is the odds ratio on the monthly adoption hazard per doubling of recent fork
rate above baseline. The forward analysis reports its effect in doublings too (`did_log2`), so
the two directions sit on a comparable log2 footing, though they are not the same estimand and
the comparison is of magnitude and sign, not like for like.

Inference is cluster-robust by repository, since a repository contributes many rows and they are
not independent. The sandwich is computed directly rather than by bootstrap: the panel runs to
hundreds of thousands of rows per practice, a two-thousand-resample cluster bootstrap of a
logistic fit at that size is not affordable, and the sandwich is exact for the same asymptotics.

Alongside the model, two statistics that do not depend on its functional form:

- a Mantel-Haenszel rate ratio comparing adoption per thousand at-risk months in surge months
  against ordinary months, pooled over strata of age and size, where a surge is at least three
  forks in the recent window at twice the baseline rate or better
- the distribution of the lag from a repository's last pre-adoption surge to its adoption

### What this cannot settle

Both directions are vulnerable to the same third cause. A repository that submits a paper or
makes its first public release tends to acquire forks and to acquire a license, a citation file
and a documentation site at about the same time, so a result in either direction may be that
event rather than either variable acting on the other. Nothing here identifies that away. What
the comparison does establish is whether the data prefer one direction, which is the specific
question a reader who doubts the precedence claim is asking.

## The retired event study

Governs `modeling/practice_event_study.py`. Its estimates should not be cited; it is superseded
by the matched difference-in-differences, for the placebo reason given above.

It still runs for one side effect. `event_study_results_license.csv` is where
`matched_did_practice_forks.py` reads the license practice's event dates, so it has to run before
the license row of that analysis can be produced. That makes the license row's treated pool
narrower than the other five practices', which read their dates straight from the event files:
its filters (`MIN_GAP_DAYS`, `MIN_DUR_DAYS`, and a fork history to measure) cut 3,568 dated
license additions to 614 before matching ever sees them. Reading `practice_events.jsonl` directly
instead admits 777 matched repositories rather than 575 and puts the effect at +0.419 doublings
rather than +0.510, with parallel trends holding either way.

Its original design, for the record: for each tool with a practice added at least `MIN_GAP` days
after its first commit, `t0` is the addition date, `rate_before` is forks per month in
`[t0 - W, t0)` clipped to the repository start, `rate_after` is forks per month in `[t0, t0 + W]`
clipped to data coverage, and the effect is `log2((rate_after + EPS) / (rate_before + EPS))`.
Aggregated with a Wilcoxon signed-rank test, a bootstrap CI on the median, and the share of tools
that accelerate, against a random pseudo-event placebo in each tool's history.

## Scoring the JOSS Tests criterion

Governs `data_collection/detect_test_evidence.py`, and the same rules in the pipeline's
`bin/analyze_joss.py`.

The pipeline formerly scored this criterion by executing each test suite and grading the pass
rate: at least 90% passing was good, at least 70% was ok, anything lower was poor, and a run that
collected no tests scored zero. That is not the criterion JOSS applies. JOSS asks whether an automated test suite exists
and is wired to continuous integration, which a reviewer establishes by looking at the repository
rather than by running it:

- **Good**: an automated test suite hooked up to continuous integration
- **OK**: documented manual steps that objectively check expected functionality, for example a
  sample input file to assert behaviour
- **Bad**: no way for a reviewer to objectively assess whether the software works

Executing suites also failed in practice: `joss_tests_score` was zero for 10,619 of 10,736 scored
repositories while roughly a third have a test directory. Static detection is both faithful to
the criterion and evaluable at cohort scale, so it replaces execution rather than approximating
it.

Onto the pipeline's existing constants:

| Score | Evidence |
|---|---|
| 1.0 | Tests present and a CI config that invokes a test runner |
| 0.7 | Tests present, but no CI, or CI that never invokes a runner. An automated suite exists and a reviewer could run it, which falls short of the Good tier's CI requirement without dropping to manual-only assessment |
| 0.3 | No tests, but sample inputs or an examples directory a reviewer could work through |
| 0.0 | No evidence a reviewer could use |

Details that matter:

- The 0.3 tier deliberately reads only sample input files and example directories, never README
  prose. The Example Usage criterion already scores documentation, and letting both criteria read
  the same evidence would make two of the five criteria measure one thing.
- Test presence is detected more broadly than ProcessRepo's check, which looks only for `tests/`,
  `test/` and top-level `*.test.py`, and so misses the common `test_*.py` inside a package
  directory and R's `tests/testthat`.
- Workflow tools verify themselves by executing the pipeline on exemplar data in CI rather than
  by running a unit-test suite, so they have no test directory and invoke no language test runner.
  `labsyspharm/mcmicro` runs three exemplar datasets end to end on every push, which is automated
  verification hooked to CI by any reviewer's reading. Missing this would penalise every workflow
  tool in the cohort, including the nf-core repositories, for choosing integration over unit
  testing.
- Tests are often invoked indirectly, through a Makefile target or a shell script, so no
  enumeration of runner commands can be complete: `psf/requests` runs its suite with `make ci`. A
  workflow that declares itself a test workflow is the more robust signal, and it is consulted
  only for repositories that already have a test suite, so a misleading name cannot by itself
  promote a repository to the Good tier.
- Measured from the default branch as cloned, matching the other Almanack checks.

The script and the pipeline compute the same flags. The pipeline is authoritative for new runs;
the script stays because it produced the table the manuscript's analysis reads, and because it
rebuilds that table from clones alone without rerunning the whole workflow across the cohort. Any
change to the tiers or the patterns has to be made in both places, or the two will disagree.

## Dating practice adoption

Each collector dates the act the corresponding check scores, mirroring the Almanack's own rules
rather than approximating them, because a looser pattern would date events for repositories the
metrics table records as failing the check.

Clones are `--filter=blob:none --no-checkout` throughout, since only path names, commit dates and
in a few cases a pickaxe search are needed. Every collector is resumable: one JSON line per
repository, appended, with repositories already present skipped.

### Citability

`data_collection/date_citability_events.py`.


An earlier pass dated only `CITATION.cff` and `codemeta.json` additions and found 307 events, too
few to characterise adoption. That undercount was not a coverage failure: the Almanack counts a
repository as citable through any of several routes, and most of the cohort's 2,586 citable
repositories use one that leaves no citation file to date. `is_citable` in the Almanack's
`garden_lattice/connectedness.py` returns True if any of these hold:

- a `CITATION.cff` or `CITATION.bib` file exists
- the README carries a citation heading (`## Citation`, `## Citing`, `## Cite`, `## How to cite`,
  or the reStructuredText equivalents)
- the README carries a shields.io DOI badge

So dating citability means dating whichever route came first, and for the README routes that means
finding the commit that introduced the heading or badge, not the earliest commit touching the
README, which for most repositories is the initial commit. Git's pickaxe does exactly this:
`git log -G<regex>` reports commits where the number of matching lines changed, so the earliest
such commit is where the text first appeared. Git fetches only the README blobs the search
touches, keeping each clone under a megabyte where a full clone would be hundreds. Every
repository is dated by the same rule, including those with a citation file, so the series is
internally consistent rather than a merge of two methods.

### Documentation artifacts

`data_collection/date_docs_events.py`.


Supplies the three file-presence practices that had no dated series: `repo_includes_contributing`
(a CONTRIBUTING file at the root or under `.github/`), `repo_includes_code_of_conduct` (a
CODE_OF_CONDUCT file at the root), and `repo_includes_common_docs` (one of twelve docsite entry
points under `docs/`). All three are decided by the Almanack from the file tree at HEAD, so the
event is the first commit that adds a qualifying file, which `git log --diff-filter=A` reports
directly. No pickaxe is needed, unlike citability. One clone dates all three, so the three
practices cost one pass rather than three.

Matching the Almanack exactly:

- `file_exists_in_repo` lowercases the expected name and compares case-insensitively, over the
  extensions `.md`, `.txt`, `.rtf` and none, so `Contributing.rtf` counts and `CONTRIBUTING.html`
  does not
- the `.github/` subdirectory is checked case-sensitively, and only for contributing; a
  CODE_OF_CONDUCT under `.github/` does not satisfy the Almanack's check, so it is not dated here
  either
- `find_file` compares docsite paths case-sensitively

### Test suites

`data_collection/date_test_events.py`.


The JOSS Tests criterion is the largest single component of the JOSS score: once scored from
static evidence, it accounts for 58% of the variance in `joss_score`, against 27% for the two
documentation-gated criteria and 12% for community guidelines. The design would otherwise have a
gap exactly where the composite carries most of its weight.

The event dated is the first commit that adds test evidence, the transition
`detect_test_evidence.py` scores as 0.0 to 0.7, and the one that separates the 6,243 no-evidence
repositories from the 3,567 with a suite. The subsequent promotion to 1.0, when continuous
integration starts invoking the suite, is not dated: that requires reading CI file contents at
every revision rather than path names alone, so it needs blobs for the whole history rather than a
blobless clone.

Test evidence is decided from path names only, which is what makes it datable
(`has_tests = has_test_dir or has_test_file or has_runner_config`), so
`git log --diff-filter=A` reports the event directly. The three components are recorded
separately, since a runner config and a test directory are different acts and their timing may
differ. Rather than restate the detector's rules, the script imports them, so a repository cannot
be dated here on evidence the detector would not have counted. The pathspecs exist only to keep
git from walking the whole tree and are deliberately broader than the rules; every path git
returns is then classified exactly.

## Owner type

Governs `data_collection/fetch_owner_type.py` and `modeling/owner_type_scores.py`. Authored by
Dave Bunten.

Section 4.3 argues that shared infrastructure raises sustainability, on evidence from 167 nf-core
pipelines and one migration case study. Owner type tests a related claim across the whole cohort:
repositories owned by an organization account carry shared conventions and continuity across
maintainers, where a personal account usually does not.

Collection keys results on the slug that was requested rather than the one returned. GitHub
silently resolves renamed repositories, so trusting the response name drops every renamed
repository from the join.

Both scores are reported because they measure different things. The JOSS score is a mean of five
review criteria and always has the same denominator. The Almanack score as stored does not: it is
out of 7 for 5,414 repositories and out of 8 for 5,361, depending on which metrics could be
retrieved, so a group difference in it could partly reflect which repositories got which
denominator. An 11-check reconstruction with a fixed denominator is therefore reported alongside
it, and agreement between the two is what makes the Almanack comparison usable.

nf-core repositories are organization-owned by construction and score far above the cohort, so the
comparison is repeated with them excluded; otherwise 167 repositories would carry part of a
difference attributed to organizations in general.

Organization repositories are also older, larger and better resourced, so the raw gap partly
measures resourcing. A regression with age, commit count and contributors as covariates is
reported next to the raw difference, and the adjusted coefficient is the one to quote.

Stars are deliberately not among those covariates, although an earlier version included them.
Section 4.2 treats stars as a consequence of these same practices, so conditioning on stars
conditions on a variable downstream of the exposure. Both versions are printed because the choice
changes a conclusion rather than a decimal place: with stars the adjusted 11-check gap reaches
t = 2.4, without them it is t = 1.9, so the Almanack gap does not survive maturity adjustment on
the defensible specification. The JOSS gap is t = 9 either way. The manuscript should therefore
rest the ownership claim on JOSS and describe the Almanack gap as pointing the same way but
marginal.
