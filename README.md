# Alberta Job Radar

The configured search excludes internships, co-ops, and student positions.
These are removed before matching, rejected locally if already queued, and
hidden from the API job pool. Regular junior, associate, and new-graduate roles
remain eligible.

Matching runs locally on every committed discovery run. Rules reject unrelated
or senior titles and explicit mandatory requirements of at least four years.
All analyst roles remain eligible; broad product, project, and adjacent roles
need at least two technical signals in their descriptions. Preferred experience
does not cause automatic rejection.

The local matcher compares named skills in job descriptions with each Markdown
resume, assigns a category, and saves an explainable overlap score. These are
heuristic scores, not guarantees of eligibility. Jobs with insufficient evidence
remain pending rather than receiving an invented score.

`--commit` runs local matching without Gemini. `--commit --match` also enables
Gemini for ambiguous jobs, lazily creating the client only when needed. No API
key is required for local matching. `GEMINI_FALLBACK_LIMIT` defaults to **2 jobs
per run**; set it to `0` to disable fallback. The production fallback uses one
attempt per job and stops further fallback requests after a quota (429) error.
Deferred jobs remain queued for a later run, and local matching continues even
when the fallback budget is exhausted. `--match-limit` limits the overall queue,
including locally resolved jobs. `GEMINI_MATCH_THRESHOLD` (default 75) applies to
both local and Gemini scores for notification qualification.

The API reapplies current relevance rules to historical jobs and hides explicit
local rejections without deleting stored records. Weak but relevant matches and
pending analyst jobs remain visible.

Jobs expire at two calendar months of age (inclusive), using the source posting
date when available and first discovery otherwise. Committed scraping runs and
API job-list requests permanently delete expired rows, including baseline jobs.
Scraping skips old source postings so they cannot return on the next run.
Date-only source values keep their calendar day; Workday's exact relative day
labels are anchored to the scrape date. Rounded or lower-bound labels are never
displayed as exact dates. Lower-bound ages can establish expiry when old enough.
