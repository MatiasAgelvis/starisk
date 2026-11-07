<script>
  import Stars from './Stars.svelte';
  import { normalizeCourseKey } from '../lib/lookup.js';
  import { REASON_MESSAGES, validateQuery } from '../lib/requests.js';
  import { verdictOf } from '../lib/verdict.js';

  let { scores = {}, teachers = {} } = $props();

  let query = $state('');
  let result = $state(null);

  // A miss can be turned into a crawl request. `lastQuery` is the text the
  // result belongs to, not the live input: editing the box without submitting
  // must not change what would be sent.
  let lastQuery = $state('');
  let requestState = $state('idle'); // idle | sending | sent | error
  let requestNote = $state('');

  const validation = $derived(lastQuery ? validateQuery(lastQuery) : null);

  function verdictLabel(record) {
    if (record.coursera == null) return 'no headline rating';
    const verdict = verdictOf(record.coursera, record.starisk);
    return verdict === 'holds-up' ? 'holds up' : verdict;
  }

  function search() {
    const raw = query.trim();
    if (!raw) return;

    lastQuery = raw;
    requestState = 'idle';
    requestNote = '';

    // A teacher profile is a different kind of thing, not a course slug. Match
    // it first so `/instructor/x` never falls through to a course lookup.
    const teacher = raw.match(/coursera\.org\/instructor\/([^/?#]+)/) ??
      raw.match(/^\/?instructor\/([^/?#]+)/);
    if (teacher) {
      const slug = decodeURIComponent(teacher[1]);
      result = { kind: 'teacher', slug, person: teachers[slug] ?? null };
      return;
    }

    const key = normalizeCourseKey(raw);
    result = { kind: 'course', key, record: scores[key] ?? null };
  }

  async function sendRequest() {
    if (requestState === 'sending' || !validation?.ok) return;

    requestState = 'sending';
    requestNote = '';

    try {
      const response = await fetch('/api/course-request', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ query: lastQuery }),
      });
      const body = await response.json().catch(() => null);

      if (response.ok && body?.ok) {
        requestState = 'sent';
        requestNote =
          body.count <= 1
            ? 'You are the first to ask for this one.'
            : `${body.count} people have asked for this one.`;
        return;
      }

      requestState = 'error';
      requestNote =
        response.status === 429
          ? 'Too many requests from this connection. Try again later.'
          : (body?.message ?? 'The request list is unavailable right now.');
    } catch {
      requestState = 'error';
      requestNote = 'The request list is unavailable right now.';
    }
  }
</script>

<div class="mx-auto w-full max-w-2xl">
  <form
    class="join w-full"
    onsubmit={(event) => {
      event.preventDefault();
      search();
    }}
  >
    <input
      class="input join-item w-full"
      bind:value={query}
      placeholder="Paste a Coursera course or teacher URL"
      aria-label="Coursera course or teacher URL"
    />
    <button class="btn join-item" type="submit">Score it</button>
  </form>

  {#if result}
    {#if result.kind === 'teacher'}
      {#if result.person}
        <div class="mt-6 rounded-box border border-base-300 p-5 text-left">
          <p class="font-display text-lg font-semibold">{result.person.name}</p>
          <a class="link link-hover mt-1 inline-block text-sm" href={`/instructors/${result.person.page}`}>
            Their courses, and how they hold up →
          </a>
        </div>
      {:else}
        <div class="alert alert-warning mt-6 text-left">
          <span>
            <span class="font-semibold">Teacher not indexed yet.</span>
            Starisk only knows the teachers on the courses it has read.
          </span>
        </div>
      {/if}
    {:else if result.record && result.record.no_reviews}
      <div class="alert alert-info mt-6 text-left">
        <span>
          <span class="font-semibold">
            {result.record.title ?? result.key}: no written reviews yet.
          </span>
          Coursera lists {result.record.ratings_total
            ? `${result.record.ratings_total.toLocaleString()} ratings`
            : 'a rating'} but no reviews, so there is nothing to weigh.
          <a
            class="link"
            href={`https://www.coursera.org/${result.record.slug ?? result.key}/reviews`}
            target="_blank"
            rel="noopener noreferrer">Check on Coursera ↗</a
          >
        </span>
      </div>
    {:else if result.record && typeof result.record.starisk === 'number'}
      <h3 class="font-display mt-6 text-left text-lg font-semibold">
        <a class="link link-hover" href={`/${result.record.slug ?? result.key}`}>
          {result.record.title ?? result.key}
        </a>
      </h3>
      <div class="stats stats-vertical mt-3 w-full shadow sm:stats-horizontal">
        <div class="stat">
          <div class="stat-title">Coursera</div>
          <div class="stat-value text-2xl">
            {result.record.coursera == null ? '—' : result.record.coursera.toFixed(1)}
          </div>
          {#if result.record.coursera != null}
            <Stars value={result.record.coursera} size={16} />
          {/if}
          <div class="stat-desc">
            {result.record.reviews}{result.record.reviews_total
              ? ` of ${result.record.reviews_total.toLocaleString()}`
              : ''} reviews read
          </div>
        </div>
        <div class="stat">
          <div class="stat-title">Starisk</div>
          <div class="stat-value text-2xl">{result.record.starisk.toFixed(1)}</div>
          <Stars value={result.record.starisk} size={16} />
          <div class="stat-desc">{verdictLabel(result.record)}</div>
        </div>
      </div>
      <a class="link link-hover mt-3 inline-block text-sm" href={`/${result.record.slug ?? result.key}`}>
        Full breakdown, including the top critical review →
      </a>
    {:else}
      <div class="alert alert-warning mt-6 text-left">
        <span>
          <span class="font-semibold">Not indexed yet.</span>
          {validation?.ok
            ? 'Starisk has only read a small set of courses so far.'
            : (validation ? REASON_MESSAGES[validation.reason] : 'This one is not among them yet.')}
        </span>
      </div>
      {#if validation?.ok}
        <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-left">
          {#if requestState === 'sent'}
            <span class="badge badge-success badge-sm">Requested</span>
            <span class="text-sm text-base-content/70">{requestNote}</span>
          {:else if requestState === 'sending'}
            <button type="button" class="btn btn-sm" disabled>
              <span class="loading loading-spinner loading-xs"></span>
              Sending…
            </button>
          {:else}
            <button type="button" class="btn btn-sm" onclick={sendRequest}>Request this course</button>
            <span class="text-xs text-base-content/60">
              Adds the name to the crawl queue. No account, no email.
            </span>
          {/if}
          {#if requestState === 'error'}
            <span class="text-sm text-error">{requestNote}</span>
          {/if}
        </div>
      {/if}
    {/if}
  {/if}
</div>
