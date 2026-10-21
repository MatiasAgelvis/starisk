<script>
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
    const gap = record.stellaid - record.coursera;
    if (gap <= -1.5) return 'contested';
    if (gap <= -0.5) return 'softened';
    return 'agrees with Coursera';
  }

  function search() {
    const key = normalize(query);
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
      <div class="stats stats-vertical mt-6 w-full shadow sm:stats-horizontal">
        <div class="stat">
          <div class="stat-title">Coursera</div>
          <div class="stat-value text-2xl">
            {result.record.coursera == null ? '—' : result.record.coursera.toFixed(1)}
          </div>
          <div class="stat-desc">{result.record.reviews} reviews read</div>
        </div>
        <div class="stat">
          <div class="stat-title">Stellaid</div>
          <div class="stat-value text-2xl">{result.record.stellaid.toFixed(2)}</div>
          <div class="stat-desc">{gapLabel(result.record)}</div>
        </div>
      </div>
    {:else}
      <div class="alert alert-warning mt-6">
        <span>
          <span class="font-mono">{result.key}</span> isn’t indexed yet. Add it to the crawl
          list and re-run.
        </span>
      </div>
    {/if}
  {/if}
</div>
