<script>
  import Stars from './Stars.svelte';
  import { verdictOf, VERDICT } from '../lib/verdict.js';

  let { rows = [] } = $props();

  let query = $state('');
  let verdict = $state('all');
  let sortKey = $state('inflation');
  let sortDir = $state('desc');

  const VERDICTS = [
    { id: 'all', label: 'All' },
    { id: 'inflated', label: 'Inflated' },
    { id: 'padded', label: 'Padded' },
    { id: 'holds-up', label: 'Holds up' },
  ];

  /** Coursera minus Starisk. Positive = the headline is above the reviews. */
  function inflationOf(row) {
    return row.coursera == null ? null : row.coursera - row.starisk;
  }

  function verdictKey(row) {
    return verdictOf(row.coursera, row.starisk);
  }

  const COLUMNS = [
    { key: 'title', label: 'Course', align: 'text-left', width: 'w-[56%] sm:w-[50%]' },
    { key: 'coursera', label: 'Coursera', align: 'text-right', width: 'w-[13%]', hide: true },
    { key: 'starisk', label: 'Starisk', align: 'text-right', width: 'w-[22%] sm:w-[13%]' },
    { key: 'inflation', label: 'Inflation', align: 'text-right', width: 'w-[22%] sm:w-[12%]' },
    { key: 'verdict', label: 'Verdict', align: 'text-left', width: 'w-[12%]', hide: true },
  ];

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
      return;
    }
    sortKey = key;
    sortDir = key === 'title' ? 'asc' : 'desc';
  }

  function ariaSort(key) {
    if (sortKey !== key) return 'none';
    return sortDir === 'asc' ? 'ascending' : 'descending';
  }

  const visible = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      if (verdict !== 'all' && verdictKey(row) !== verdict) return false;
      if (!needle) return true;
      return `${row.title ?? ''} ${row.provider ?? ''} ${row.slug}`.toLowerCase().includes(needle);
    });
    return [...filtered].sort(compare);
  });
</script>

<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
  <div class="flex flex-wrap gap-2">
    {#each VERDICTS as option (option.id)}
      <button
        class="btn btn-sm whitespace-nowrap {verdict === option.id ? 'btn-neutral' : 'btn-ghost'}"
        aria-pressed={verdict === option.id}
        onclick={() => (verdict = option.id)}
      >
        {option.label}
      </button>
    {/each}
  </div>

  <div class="flex items-center gap-3">
    <input
      class="input input-sm w-full sm:w-64"
      bind:value={query}
      placeholder="Filter by course, provider…"
      aria-label="Filter courses"
    />
    <span class="whitespace-nowrap text-xs text-base-content/60">
      {visible.length} of {rows.length}
    </span>
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
                  {row.provider ?? 'Unknown provider'}
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

  {#if visible.length === 0}
    <p class="py-8 text-center text-sm text-base-content/60">
      No course matches that filter.
    </p>
  {/if}
</div>
