<script>
  import Stars from './Stars.svelte';
  import { typeLabel } from '../lib/groupings.js';
  import { ariaSortFor, compareValues, paginate, toggleSort } from '../lib/table.js';

  let { rows = [], pageSize = 25 } = $props();

  let query = $state('');
  let type = $state('all');
  let sortKey = $state('average');
  let sortDir = $state('desc');
  let page = $state(1);

  const TYPES = [
    { id: 'all', label: 'All' },
    { id: 'specialization', label: 'Specializations' },
    { id: 'professional-certificate', label: 'Professional Certificates' },
  ];

  const COLUMNS = [
    { key: 'title', label: 'Program', align: 'text-left', width: 'w-[54%] sm:w-[42%]' },
    { key: 'courses', label: 'Courses', align: 'text-right', width: 'w-[16%] sm:w-[14%]' },
    { key: 'average', label: 'Avg', align: 'text-right', width: 'w-[18%] sm:w-[14%]' },
    { key: 'low', label: 'Range', align: 'text-right', width: 'w-[16%]', hide: true },
    { key: 'reviews', label: 'Reviews read', align: 'text-right', width: 'w-[14%]', hide: true },
  ];

  function value(row, key) {
    if (key === 'title') return (row.title ?? row.key).toLowerCase();
    if (key === 'type') return typeLabel(row.type).toLowerCase();
    if (key === 'courses') return row.scored;
    return row[key] ?? null;
  }

  function compare(a, b) {
    return compareValues(value(a, sortKey), value(b, sortKey), sortDir);
  }

  function sortBy(key) {
    const next = toggleSort(key, sortKey, sortDir, 'title');
    sortKey = next.key;
    sortDir = next.direction;
    page = 1;
  }

  function pickType(id) {
    type = id;
    page = 1;
  }

  function search(event) {
    query = event.currentTarget.value;
    page = 1;
  }

  function clearFilters() {
    query = '';
    type = 'all';
    page = 1;
  }

  function ariaSort(key) {
    return ariaSortFor(key, sortKey, sortDir);
  }

  const typeCounts = $derived.by(() => {
    const counts = new Map();
    for (const row of rows) counts.set(row.type, (counts.get(row.type) ?? 0) + 1);
    return counts;
  });

  const filtered = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (type !== 'all' && row.type !== type) return false;
      if (!needle) return true;
      return `${row.title ?? ''} ${row.provider ?? ''} ${typeLabel(row.type)}`
        .toLowerCase()
        .includes(needle);
    });
  });

  const ordered = $derived.by(() => [...filtered].sort(compare));
  const paging = $derived(paginate(ordered, page, pageSize));
  const pageCount = $derived(paging.pageCount);
  const current = $derived(paging.current);
  const visible = $derived(paging.visible);
  const first = $derived(paging.first);
  const last = $derived(paging.last);
  const narrowed = $derived(ordered.length !== rows.length);
</script>

<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
  <div class="flex flex-wrap gap-2">
    {#each TYPES as option (option.id)}
      <button
        class="btn btn-sm whitespace-nowrap {type === option.id ? 'btn-neutral' : 'btn-ghost'}"
        aria-pressed={type === option.id}
        onclick={() => pickType(option.id)}
      >
        {option.label}
        <span class="opacity-50">
          {option.id === 'all' ? rows.length : (typeCounts.get(option.id) ?? 0)}
        </span>
      </button>
    {/each}
  </div>
  <input
    class="input input-sm w-full sm:w-64"
    value={query}
    oninput={search}
    placeholder="Filter by program or provider…"
    aria-label="Filter programs"
  />
</div>

<div>
  <table class="table table-zebra w-full table-fixed">
    <thead>
      <tr>
        {#each COLUMNS as column (column.key)}
          <th
            class="{column.align} {column.width} {column.hide ? 'hidden sm:table-cell' : ''}"
            aria-sort={ariaSort(column.key)}
          >
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
      {#each visible as row (row.key)}
        <tr>
          <td>
            <div class="min-w-0">
              <div class="truncate font-medium">
                <a class="link link-hover" href={`/programs/${row.key}`}>{row.title}</a>
              </div>
              <div class="truncate text-xs text-base-content/50">
                {row.provider ?? 'Unknown provider'}{' · '}{typeLabel(row.type)}
              </div>
            </div>
          </td>
          <td class="text-right font-mono text-sm">{row.scored}/{row.total}</td>
          <td class="text-right">
            <div class="flex items-center justify-end gap-2">
              <span class="font-bold">{row.average == null ? '—' : row.average.toFixed(1)}</span>
              {#if row.average != null}
                <span class="hidden md:inline-flex"><Stars value={row.average} /></span>
              {/if}
            </div>
          </td>
          <td class="hidden whitespace-nowrap text-right font-mono text-sm sm:table-cell">
            {row.low == null ? '—' : `${row.low.toFixed(1)}–${row.high.toFixed(1)}`}
          </td>
          <td class="hidden text-right font-mono text-sm sm:table-cell">{row.reviews}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  {#if ordered.length === 0}
    <div class="py-10 text-center text-sm text-base-content/60">
      <p>No program matches those filters.</p>
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
