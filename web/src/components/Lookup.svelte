<script>
  import Stars from './Stars.svelte';
  import { requestHref } from '../lib/config.js';

  let { scores = {}, teachers = {} } = $props();

  let query = $state('');
  let result = $state(null);

  function normalize(input) {
    const match = input.trim().match(/coursera\.org\/([^/?#]+)\/([^/?#]+)/);
    if (match) return `${match[1]}/${match[2]}`;
    return input.trim().replace(/^\/+|\/+$/g, '');
  }

  function verdictLabel(record) {
    if (record.coursera == null) return 'no headline rating';
    const inflation = record.coursera - record.starisk;
    if (inflation >= 1.5) return 'inflated';
    if (inflation >= 0.5) return 'padded';
    return 'holds up';
  }

  function search() {
    const raw = query.trim();
    if (!raw) return;

    // A teacher profile is a different kind of thing, not a course slug. Match
    // it first so `/instructor/x` never falls through to a course lookup.
    const teacher = raw.match(/coursera\.org\/instructor\/([^/?#]+)/) ??
      raw.match(/^\/?instructor\/([^/?#]+)/);
    if (teacher) {
      const slug = decodeURIComponent(teacher[1]);
      result = { kind: 'teacher', slug, person: teachers[slug] ?? null };
      return;
    }

    const key = normalize(raw);
    result = { kind: 'course', key, record: scores[key] ?? null };
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
    {:else if result.record}
      <h3 class="font-display mt-6 text-left text-lg font-semibold">
        <a class="link link-hover" href={`/${result.record.slug}`}>
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
      <a class="link link-hover mt-3 inline-block text-sm" href={`/${result.record.slug}`}>
        Full breakdown, including the top critical review →
      </a>
    {:else}
      <div class="alert alert-warning mt-6 text-left">
        <span>
          <span class="font-semibold">Not indexed yet.</span>
          Starisk has only read a small set of courses so far.
          {#if requestHref(result.key)}
            <a class="link" href={requestHref(result.key)}>Ask for this one</a>.
          {:else}
            This one isn't among them yet.
          {/if}
        </span>
      </div>
    {/if}
  {/if}
</div>
