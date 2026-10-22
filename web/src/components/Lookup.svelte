<script>
  import Stars from './Stars.svelte';
  import { requestHref } from '../lib/config.js';

  let { scores = {} } = $props();

  let query = $state('');
  let result = $state(null);

  function normalize(input) {
    const match = input.trim().match(/coursera\.org\/([^/?#]+)\/([^/?#]+)/);
    if (match) return `${match[1]}/${match[2]}`;
    return input.trim().replace(/^\/+|\/+$/g, '');
  }

  function gapLabel(record) {
    if (record.coursera == null) return 'no headline rating';
    const gap = record.starisk - record.coursera;
    if (gap <= -1.5) return 'contested';
    if (gap <= -0.5) return 'softened';
    return 'agrees with Coursera';
  }

  function search() {
    const key = normalize(query);
    if (!key) return;
    result = { key, record: scores[key] ?? null };
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
      placeholder="Paste a Coursera course URL"
      aria-label="Coursera course URL"
    />
    <button class="btn join-item" type="submit">Score it</button>
  </form>

  {#if result}
    {#if result.record}
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
          <div class="stat-desc">{gapLabel(result.record)}</div>
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
