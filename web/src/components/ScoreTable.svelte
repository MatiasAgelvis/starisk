<script>
  import Stars from './Stars.svelte';
  import { verdictOf, VERDICT } from '../lib/verdict.js';

  let { rows = [], pageSize = 25 } = $props();

  let query = $state('');
  let verdict = $state('all');
  let topic = $state('all');
  // A ranking whose second row has one review is noise, so tiny samples are
  // hidden by default — but the count below always says how many are hidden, and
  // the toggle is one click away. Never hide them silently.
  let hideLow = $state(true);
  let sortKey = $state('inflation');
  let sortDir = $state('desc');
  let page = $state(1);

  const VERDICTS = [
    { id: 'all', label: 'All' },
    { id: 'inflated', label: 'Inflated' },
    { id: 'padded', label: 'Padded' },
    { id: 'holds-up', label: 'Holds up' },
  ];

  const COLUMNS = [
    { key: 'title', label: 'Course', align: 'text-left', width: 'w-[56%] sm:w-[50%]' },
    { key: 'coursera', label: 'Coursera', align: 'text-right', width: 'w-[13%]', hide: true },
    { key: 'starisk', label: 'Starisk', align: 'text-right', width: 'w-[22%] sm:w-[13%]' },
    { key: 'inflation', label: 'Inflation', align: 'text-right', width: 'w-[22%] sm:w-[12%]' },
    { key: 'verdict', label: 'Verdict', align: 'text-left', width: 'w-[12%]', hide: true },
  ];

  /** Coursera minus Starisk. Positive = the headline is above the reviews. */
  function inflationOf(row) {
    return row.coursera == null ? null : row.coursera - row.starisk;
  }

  function verdictKey(row) {
    return verdictOf(row.coursera, row.starisk);
  }

  function value(row, key) {
    if (key === 'title') return (row.title ?? row.slug).toLowerCase();
    if (key === 'inflation' || key === 'verdict') return inflationOf(row);
    return row[key] ?? null;
  }

  function compare(a, b) {
    const av = value(a, sortKey);
    const bv = value(b, sortKey);
    if (av == null && bv == null) return 0;
    if (av == null) return 1; // unknown always last
    if (bv == null) return -1;
    const result = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
    return sortDir === 'asc' ? result : -result;
  }

  function sortBy(key) {
    if (sortKey === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey = key;
      sortDir = key === 'title' ? 'asc' : 'desc';
    }
    page = 1;
  }

  function pickVerdict(id) {
    verdict = id;
    page = 1;
  }

  function pickTopic(id) {
    topic = id;
    page = 1;
  }

  function toggleLow() {
    hideLow = !hideLow;
    page = 1;
  }

  function search(event) {
    query = event.currentTarget.value;
    page = 1;
  }

  function clearFilters() {
    query = '';
    verdict = 'all';
    topic = 'all';
    hideLow = true;
    page = 1;
  }

  function ariaSort(key) {
    if (sortKey !== key) return 'none';
    return sortDir === 'asc' ? 'ascending' : 'descending';
  }

  const lowCount = $derived(rows.filter((row) => row.low).length);

  // Topics come from the data, ordered by how many courses each one covers.
  // Counts are shown because they also say how much of the corpus a filter keeps.
  const topics = $derived.by(() => {
    const counts = new Map();
    for (const row of rows) {
      for (const name of row.categories ?? []) {
        counts.set(name, (counts.get(name) ?? 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  });

  const filtered = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (hideLow && row.low) return false;
      if (verdict !== 'all' && verdictKey(row) !== verdict) return false;
      if (topic !== 'all' && !(row.categories ?? []).includes(topic)) return false;
      if (!needle) return true;
      return `${row.title ?? ''} ${row.provider ?? ''} ${row.slug}`
        .toLowerCase()
        .includes(needle);
    });
  });

  const ordered = $derived.by(() => [...filtered].sort(compare));
  const pageCount = $derived(Math.max(1, Math.ceil(ordered.length / pageSize)));
  // Clamp instead of trusting `page`: a filter can shrink the list under it.
  const current = $derived(Math.min(page, pageCount));
  const visible = $derived(
    ordered.slice((current - 1) * pageSize, current * pageSize),
  );
  const first = $derived(ordered.length === 0 ? 0 : (current - 1) * pageSize + 1);
  const last = $derived(Math.min(current * pageSize, ordered.length));
  const narrowed = $derived(ordered.length !== rows.length);
</script>

<div class="mb-4 flex flex-col gap-3">
  <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
    <div class="flex flex-wrap gap-2">
      {#each VERDICTS as option (option.id)}
        <button
          class="btn btn-sm whitespace-nowrap {verdict === option.id ? 'btn-neutral' : 'btn-ghost'}"
          aria-pressed={verdict === option.id}
          onclick={() => pickVerdict(option.id)}
        >
          {option.label}
        </button>
      {/each}
      <button
        class="btn btn-sm whitespace-nowrap {hideLow ? 'btn-neutral' : 'btn-ghost'}"
        aria-pressed={hideLow}
        onclick={toggleLow}
      >
        Hide small samples{#if lowCount} <span class="opacity-50">{lowCount}</span>{/if}
      </button>
    </div>

    <input
      class="input input-sm w-full sm:w-56"
      value={query}
      oninput={search}
      placeholder="Filter by course, provider…"
      aria-label="Filter courses"
    />
  </div>

  <div class="flex flex-wrap items-center gap-1.5">
    <span class="mr-0.5 text-[0.65rem] font-semibold uppercase tracking-wider text-base-content/40">
      Topic
    </span>
    <button
      class="btn btn-xs whitespace-nowrap {topic === 'all' ? 'btn-neutral' : 'btn-ghost'}"
      aria-pressed={topic === 'all'}
      onclick={() => pickTopic('all')}
    >
      All <span class="opacity-50">{rows.length}</span>
    </button>
    {#each topics as [name, count] (name)}
      <button
        class="btn btn-xs whitespace-nowrap {topic === name ? 'btn-neutral' : 'btn-ghost'}"
        aria-pressed={topic === name}
        onclick={() => pickTopic(name)}
      >
        {name} <span class="opacity-50">{count}</span>
      </button>
    {/each}
  </div>
</div>

<!-- No overflow container: the table is fixed-width with truncating cells, so
     anything wider than the viewport would be a bug — and a nested scroller
     swallows vertical drags on phones. -->
<div>
  <table class="table table-zebra w-full table-fixed">
    <thead>
      <tr>
        {#each COLUMNS as column (column.key)}
          <th class="{column.align} {column.width} {column.hide ? 'hidden sm:table-cell' : ''}" aria-sort={ariaSort(column.key)}>
            <button
              class="inline-flex items-center gap-1 font-semibold hover:underline"
              onclick={() => sortBy(column.key)}
            >
              {column.label}
              <span class="text-[0.6rem] text-base-content/50" aria-hidden="true">
                {sortKey === column.key ? (sortDir === 'asc' ? '▲' : '▼') : ''}
              </span>
            </button>
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each visible as row (row.slug)}
        {@const inflation = inflationOf(row)}
        {@const style = VERDICT[verdictKey(row)]}
        <tr>
          <td>
            <div class="flex items-center gap-3">
              <span
                class="inline-flex h-8 w-14 shrink-0 items-center justify-center rounded bg-white p-1 ring-1 ring-base-300/60"
              >
                <img
                  src={row.image ?? '/coursera-logo.png'}
                  alt=""
                  class="h-full w-full object-contain drop-shadow-[0_0_1px_rgba(0,0,0,0.6)]"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                />
              </span>
              <div class="min-w-0">
                <div class="truncate font-medium">
                  <a class="link link-hover" href={`/${row.slug}`}>{row.title ?? row.slug}</a>
                </div>
                <div class="truncate text-xs text-base-content/50">
                  {row.provider ?? 'Unknown provider'}{#if row.low}<span class="text-warning/80"> · low sample</span>{/if}
                </div>
              </div>
            </div>
          </td>
          <td class="hidden text-right sm:table-cell">
            <div class="flex items-center justify-end gap-2">
              <span>{row.coursera == null ? '—' : row.coursera.toFixed(1)}</span>
              {#if row.coursera != null}<span class="hidden md:inline-flex"><Stars value={row.coursera} /></span>{/if}
            </div>
          </td>
          <td class="text-right">
            <div class="flex items-center justify-end gap-2">
              <span class="font-bold">{row.starisk.toFixed(1)}</span>
              <span class="hidden md:inline-flex"><Stars value={row.starisk} /></span>
            </div>
          </td>
          <td class="text-right">
            <div class="flex items-center justify-end gap-2">
              <span class="font-mono text-sm">
                {inflation == null ? '—' : inflation.toFixed(1)}
              </span>
              <span
                class="hidden h-1.5 rounded-full sm:inline-block {style.bar}"
                style={`width:${inflation == null ? 0 : Math.min(Math.max(inflation, 0) / 3, 1) * 44}px`}
                aria-hidden="true"
              ></span>
            </div>
          </td>
          <td class="hidden sm:table-cell"><span class="badge whitespace-nowrap {style.badge}">{style.label}</span></td>
        </tr>
      {/each}
    </tbody>
  </table>

  {#if ordered.length === 0}
    <div class="py-10 text-center text-sm text-base-content/60">
      <p>No course matches those filters.</p>
      <button class="btn btn-sm btn-ghost mt-3" onclick={clearFilters}>Reset filters</button>
    </div>
  {:else}
    <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-base-content/60" aria-live="polite">
        Showing {first}–{last} of {ordered.length}{narrowed ? ` (${rows.length} total)` : ''}
      </p>
      {#if pageCount > 1}
        <div class="join">
          <button
            class="btn btn-sm join-item"
            disabled={current === 1}
            onclick={() => (page = current - 1)}
            aria-label="Previous page">‹ Prev</button
          >
          <span class="btn btn-sm join-item btn-disabled" aria-current="page">
            Page {current} / {pageCount}
          </span>
          <button
            class="btn btn-sm join-item"
            disabled={current === pageCount}
            onclick={() => (page = current + 1)}
            aria-label="Next page">Next ›</button
          >
        </div>
      {/if}
    </div>
  {/if}
</div>
