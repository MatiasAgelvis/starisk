<script>
  import Stars from './Stars.svelte';
  import { normalizeCourseKey } from '../lib/lookup.js';
  import { REASON_MESSAGES, validateQuery } from '../lib/requests.js';
  import { buildSearchIndex, search } from '../lib/search.js';
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

  // Type-ahead. The index is built once; scoring 600 titles on a keystroke is
  // cheaper than debouncing it.
  const index = buildSearchIndex(scores, teachers);
  let focused = $state(false);
  let activeIndex = $state(-1);

  // A link is trusted only as an exact key; fuzzy matching it would let a typo'd
  // host resolve to some unrelated course. A link with no match also keeps the
  // panel closed, so typing a URL is not a stream of "no match" rows.
  const LOOKS_LIKE_LINK =
    /^(?:[a-z][a-z0-9+.-]*:\/\/|www\.)|coursera\.org\/|^\/?(?:learn|specializations|professional-certificates|instructor)\//i;

  const suggestions = $derived(
    focused && query.trim().length >= 2 ? search(index, query) : [],
  );
  const open = $derived(
    focused &&
      query.trim().length >= 2 &&
      (suggestions.length > 0 || !LOOKS_LIKE_LINK.test(query)),
  );
  const validation = $derived(lastQuery ? validateQuery(lastQuery) : null);

  // The payload only carries courses that can be answered, so its size is an
  // honest "read so far" number for the miss state. Scored-only matches the
  // leaderboard's own count, rather than including courses with no reviews.
  const scoredCount = Object.values(scores).filter(
    (record) => typeof record.starisk === 'number',
  ).length;

  function verdictLabel(record) {
    if (record.coursera == null) return 'no headline rating';
    const verdict = verdictOf(record.coursera, record.starisk);
    return verdict === 'holds-up' ? 'holds up' : verdict;
  }

  function subtitle(item) {
    if (item.kind === 'teacher') return 'Instructor';
    if (item.noReviews) {
      return item.provider ? `${item.provider} · No written reviews` : 'No written reviews';
    }
    const rating =
      item.coursera == null ? 'No headline rating' : `Coursera ${item.coursera.toFixed(1)}`;
    return item.provider ? `${item.provider} · ${rating}` : rating;
  }

  function lookup() {
    const raw = query.trim();
    if (!raw) return;

    focused = false;
    activeIndex = -1;
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
    let matchedKey = key;
    let record = scores[key] ?? null;

    // A typed title is not a slug. When the exact key misses and the input is
    // not a link, ask the same matcher that powers the dropdown for its best
    // guess — otherwise "Financial Markets" would always end in a request.
    if (!record && !LOOKS_LIKE_LINK.test(raw)) {
      const [best] = search(index, raw, 1);
      if (best?.kind === 'course') {
        matchedKey = best.key;
        record = scores[best.key] ?? null;
      } else if (best?.kind === 'teacher') {
        result = {
          kind: 'teacher',
          slug: best.slug,
          person: teachers[best.slug] ?? null,
        };
        return;
      }
    }

    result = { kind: 'course', key: matchedKey, record };
  }

  function onKeydown(event) {
    if (event.key === 'Escape' && open) {
      focused = false;
      activeIndex = -1;
      return;
    }

    if (!open || suggestions.length === 0) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % suggestions.length;
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = activeIndex <= 0 ? suggestions.length - 1 : activeIndex - 1;
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      window.location.assign(suggestions[activeIndex].href);
    }
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

<div class="mx-auto w-full max-w-2xl text-left">
  <div class="relative">
    <form
      class="join w-full"
      role="search"
      aria-label="Find a course or teacher"
      onsubmit={(event) => {
        event.preventDefault();
        lookup();
      }}
    >
      <input
        class="input join-item w-full"
        bind:value={query}
        placeholder="Search courses and teachers"
        aria-label="Search Coursera courses and teachers"
        role="combobox"
        aria-expanded={open}
        aria-controls={open ? 'lookup-suggestions' : undefined}
        aria-autocomplete="list"
        aria-activedescendant={open && activeIndex >= 0
          ? `lookup-option-${activeIndex}`
          : undefined}
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        enterkeyhint="search"
        onfocus={() => (focused = true)}
        onblur={() => {
          focused = false;
          activeIndex = -1;
        }}
        oninput={() => {
          focused = true;
          activeIndex = -1;
        }}
        onkeydown={onKeydown}
      />
      <button class="btn join-item" type="submit">Score it</button>
    </form>

    {#if open}
      <!-- Kept mousedown on the panel so the input keeps focus while a row is
           clicked; otherwise the blur handler removes the row before the click. -->
      <div
        id="lookup-suggestions"
        class="absolute inset-x-0 top-full z-50 mt-2 overflow-hidden rounded-box border border-base-300 bg-base-100 p-1 shadow-xl"
        onmousedown={(event) => event.preventDefault()}
      >
        {#if suggestions.length > 0}
          <ul role="listbox" aria-label="Matches" class="m-0 list-none p-0">
            {#each suggestions as item, i (item.key)}
              <li role="presentation">
                <a
                  id={`lookup-option-${i}`}
                  role="option"
                  aria-selected={i === activeIndex}
                  href={item.href}
                  class="flex items-center gap-3 rounded-field px-3 py-2"
                  class:bg-base-200={i === activeIndex}
                  onmouseenter={() => (activeIndex = i)}
                >
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-sm font-medium">{item.title}</span>
                    <span class="block truncate text-xs text-base-content/60">
                      {subtitle(item)}
                    </span>
                  </span>
                  {#if item.kind === 'course' && item.starisk != null}
                    <span class="shrink-0 text-right">
                      <span class="block text-sm font-semibold tabular-nums">
                        {item.starisk.toFixed(1)}
                      </span>
                      <span class="block text-[10px] uppercase tracking-wide text-base-content/50">
                        Starisk
                      </span>
                    </span>
                  {/if}
                </a>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="px-3 py-2 text-sm text-base-content/60">
            No match. Press Enter to ask for this one.
          </p>
        {/if}
      </div>
    {/if}
  </div>

  {#if !result && !open}
    <p class="mt-2 text-xs text-base-content/50">
      Search by title, or paste a Coursera course or teacher link.
    </p>
  {/if}

  <!-- A permanently rendered live region: screen readers announce reliably only
       when the region already exists. The score block keeps the site's `stats`
       treatment; every other answer is the hairline card the teacher result
       already used, so a miss and a hit read as the same kind of thing. -->
  {#snippet requestAction(buttonLabel, hint)}
    <div class="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
      {#if requestState === 'sent'}
        <span class="badge badge-ghost badge-sm gap-1">
          <span aria-hidden="true">✓</span> Requested
        </span>
        <span class="text-sm text-base-content/60">{requestNote}</span>
      {:else if requestState === 'sending'}
        <button type="button" class="btn btn-sm" disabled>
          <span class="loading loading-spinner loading-xs"></span>
          Sending…
        </button>
      {:else}
        <button type="button" class="btn btn-sm" onclick={sendRequest}>{buttonLabel}</button>
        <span class="text-xs text-base-content/60">{hint}</span>
      {/if}
      {#if requestState === 'error'}
        <span class="text-sm text-error">{requestNote}</span>
      {/if}
    </div>
  {/snippet}

  <div class="text-left" class:mt-6={Boolean(result)} aria-live="polite">
    {#if result}
      {#if result.kind === 'teacher'}
        {#if result.person}
          <div class="rounded-box border border-base-300 p-5">
            <p class="font-display text-lg font-semibold">{result.person.name}</p>
            <a
              class="link link-hover mt-1 inline-block text-sm"
              href={`/instructors/${result.person.page}`}
            >
              Their courses, and how they hold up →
            </a>
          </div>
        {:else}
          <div class="rounded-box border border-base-300 p-5">
            <p class="font-display text-lg font-semibold">Teacher not indexed yet</p>
            <p class="mt-1 text-sm text-base-content/70">
              Starisk only knows the teachers on the courses it has read.
            </p>
            {#if validation?.ok}
              {@render requestAction(
                'Request this instructor',
                'Adds their courses to the crawl queue. No account, no email.',
              )}
            {/if}
          </div>
        {/if}
      {:else if result.record && result.record.no_reviews}
        <div class="rounded-box border border-base-300 p-5">
          <div class="flex flex-wrap items-center gap-2">
            <p class="font-display text-lg font-semibold">
              {result.record.title ?? result.key}
            </p>
            <span class="badge badge-ghost badge-sm">No written reviews</span>
          </div>
          <p class="mt-1 text-sm text-base-content/70">
            Coursera lists {result.record.ratings_total
              ? `${result.record.ratings_total.toLocaleString()} ratings`
              : 'a rating'} but no reviews, so there is nothing to weigh.
          </p>
          <a
            class="link link-hover mt-3 inline-block text-sm"
            href={`https://www.coursera.org/${result.record.slug ?? result.key}/reviews`}
            target="_blank"
            rel="noopener noreferrer">Check on Coursera ↗</a
          >
        </div>
      {:else if result.record && typeof result.record.starisk === 'number'}
        <h3 class="font-display text-lg font-semibold">
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
        <a
          class="link link-hover mt-3 inline-block text-sm"
          href={`/${result.record.slug ?? result.key}`}
        >
          Full breakdown, including the top critical review →
        </a>
      {:else if validation?.ok}
        <div class="rounded-box border border-base-300 p-5">
          <p class="font-display text-lg font-semibold">Not indexed yet</p>
          <p class="mt-1 text-sm text-base-content/70">
            Starisk has scored {scoredCount} courses so far — this isn't one of them.
          </p>
          {@render requestAction(
            'Request this course',
            'Adds it to the crawl queue. No account, no email.',
          )}
        </div>
      {:else}
        <div class="rounded-box border border-base-300 p-5">
          <p class="font-display text-lg font-semibold">That doesn't look like a course</p>
          <p class="mt-1 text-sm text-base-content/70">
            {validation ? REASON_MESSAGES[validation.reason] : 'Try a Coursera course link.'}
          </p>
        </div>
      {/if}
    {/if}
  </div>
</div>
