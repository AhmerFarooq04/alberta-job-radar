import { useEffect, useState } from "react";

type Period = "today" | "week" | "month";

const columns = [
  { id: "data_analytics", label: "Data & Analytics" },
  { id: "software_development", label: "Programming" },
  { id: "it_systems", label: "IT & Systems" },
  { id: "business_analyst", label: "Business & Analyst" },
  { id: "tech_adjacent_other", label: "Tech-Adjacent & Other" },
] as const;

type Category = (typeof columns)[number]["id"];

type Job = {
  fingerprint: string;
  title: string;
  company_name: string;
  job_url: string;
  posted_at: string | null;
  posted_text: string | null;
  first_seen_at: string;
  category: string;
  gemini_status: string;
  match_score: number | null;
};

type JobsResponse = {
  jobs: Job[];
  total: number;
};

const periods: { value: Period; label: string; hint: string }[] = [
  { value: "today", label: "Day", hint: "Discovered today in Edmonton time" },
  { value: "week", label: "Week", hint: "Discovered in the last 7 days" },
  { value: "month", label: "Month", hint: "Discovered in the last 30 days" },
];

function categoryOf(job: Job): Category {
  return columns.some((column) => column.id === job.category)
    ? (job.category as Category)
    : "tech_adjacent_other";
}

function shadeOf(job: Job): string {
  if (
    !["qualified", "rejected"].includes(job.gemini_status) ||
    job.match_score === null ||
    !Number.isFinite(job.match_score)
  ) {
    return "unscored";
  }

  if (job.match_score >= 75) return "strong";
  if (job.match_score >= 50) return "possible";
  return "weak";
}

function matchLabel(job: Job): string {
  if (shadeOf(job) !== "unscored") {
    return `Match score: ${job.match_score}%`;
  }

  return job.gemini_status === "error"
    ? "Scoring unavailable"
    : "Not yet scored";
}

function shortDate(value: string): string | null {
  // Preserve a source's date-only value without timezone shifting.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const date = new Date(`${value}T12:00:00Z`);
    if (Number.isNaN(date.getTime())) return null;

    return date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleDateString("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "America/Edmonton",
  });
}

function dateLabel(job: Job): { label: string; hint: string } {
  if (job.posted_at) {
    const formatted = shortDate(job.posted_at);
    if (formatted) {
      return { label: formatted, hint: `Posted ${formatted}` };
    }
  }

  // Relative source dates can become stale after a scrape.
  // Show an explicitly labelled discovery date instead.
  const discovered = shortDate(job.first_seen_at);

  return {
    label: discovered ? `Seen ${discovered}` : "Date unknown",
    hint: "Posted date unavailable; showing when Job Radar discovered it",
  };
}

function safeUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function JobCard({ job }: { job: Job }) {
  const date = dateLabel(job);
  const href = safeUrl(job.job_url);
  const className = `job-card ${shadeOf(job)}`;

  const contents = (
    <>
      <h3>{job.title}</h3>
      <div className="card-footer">
        <span className="company" title={job.company_name}>
          {job.company_name}
        </span>
        <span className="date" title={date.hint}>
          {date.label}
        </span>
      </div>
    </>
  );

  if (!href) {
    return (
      <article
        className={`${className} unavailable`}
        aria-label={`${job.title}. Application link unavailable.`}
        title="Application link unavailable"
      >
        {contents}
      </article>
    );
  }

  return (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={matchLabel(job)}
      aria-label={`${job.title}, ${job.company_name}. ${date.hint}. ${matchLabel(job)}. Opens in a new tab.`}
    >
      {contents}
    </a>
  );
}

export default function App() {
  const [period, setPeriod] = useState<Period>("today");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let timedOut = false;

    setLoading(true);
    setError("");
    setJobs([]);

    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 15000);

    async function load() {
      try {
        const response = await fetch(`/api/jobs?period=${period}`, {
          signal: controller.signal,
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }

        const data: JobsResponse = await response.json();

        if (!Array.isArray(data.jobs)) {
          throw new Error("Invalid job response");
        }

        if (active) setJobs(data.jobs);
      } catch {
        if (active) {
          setError(
            timedOut
              ? "The request timed out. Try again."
              : "Could not load jobs. Check that the API is running.",
          );
        }
      } finally {
        window.clearTimeout(timeout);
        if (active) setLoading(false);
      }
    }

    void load();

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [period, retry]);

  return (
    <main className="app">
      <header className="toolbar">
        <h1>
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            aria-hidden="true"
          >
            <rect x="2" y="3" width="16" height="14" rx="2" />
            <path d="M7.3 3v14M12.7 3v14" />
            <path d="M4.5 6h.5M9.5 6h.5M14.8 6h.5" />
          </svg>
          JOB RADAR
        </h1>

        <div className="periods" role="group" aria-label="Discovery period">
          {periods.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={period === item.value}
              title={item.hint}
              onClick={() => setPeriod(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="error-message" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setRetry((value) => value + 1)}>
            Retry
          </button>
        </div>
      )}

      <span className="sr-only" role="status">
        {loading ? "Loading jobs" : error || `${jobs.length} jobs loaded`}
      </span>

      <div className="board" aria-busy={loading}>
        {columns.map((column) => {
          const items = jobs.filter((job) => categoryOf(job) === column.id);

          return (
            <section
              key={column.id}
              className="column"
              aria-labelledby={`column-${column.id}`}
            >
              <header className="column-header">
                <h2 id={`column-${column.id}`}>{column.label}</h2>
                <span className="count">{loading ? "—" : items.length}</span>
              </header>

              <div className="column-body">
                {loading ? (
                  <p className="empty">Loading…</p>
                ) : error ? (
                  <p className="empty">Jobs unavailable</p>
                ) : items.length === 0 ? (
                  <p className="empty">No new jobs</p>
                ) : (
                  items.map((job) => (
                    <JobCard key={job.fingerprint} job={job} />
                  ))
                )}
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}