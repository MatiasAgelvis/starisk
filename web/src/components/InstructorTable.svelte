<script>
  import Stars from './Stars.svelte';
  import { initials } from '../lib/instructors.js';
  import { ariaSortFor, compareValues, paginate, toggleSort } from '../lib/table.js';

  let { rows = [], pageSize = 25 } = $props();

  let query = $state('');
  let sortKey = $state('courses');
  let sortDir = $state('desc');
  let multiOnly = $state(false);
  let page = $state(1);

  // Default order is "most courses first" — a directory, not a podium. The
  // average is sortable because a visitor will want it, and pretending otherwise
  // would just be a table that fights its reader.
  // The numeric columns are sized to their content rather than as percentages:
  // the page is max-w-4xl, and a percentage of it is narrower than the score
  // plus its stars, which would spill into the next cell. The name takes the rest.
  const COLUMNS = [
    { key: 'name', label: 'Teacher', align: 'text-left', width: 'w-auto' },
    { key: 'courses', label: 'Courses', align: 'text-right', width: 'w-24' },
    { key: 'average', label: 'Avg', align: 'text-right', width: 'w-[6rem] md:w-[9.5rem]' },
    { key: 'low', label: 'Min', align: 'text-right', width: 'w-[5rem]', hide: true },
    { key: 'high', label: 'Max', align: 'text-right', width: 'w-[5rem]', hide: true },
    { key: 'reviews', label: 'Reviews read', align: 'text-right', width: 'w-[8rem]', hide: true },
  ];

  function value(row, key) {
    if (key === 'name') return (row.name ?? row.page).toLowerCase();
    return row[key] ?? null;
  }

  function compare(a, b) {
    return compareValues(value(a, sortKey), value(b, sortKey), sortDir);
  }

  function sortBy(key) {
    const next = toggleSort(key, sortKey, sortDir, 'name');
    sortKey = next.key;
    sortDir = next.direction;
    page = 1;
  }

  function search(event) {
    query = event.currentTarget.value;
    page = 1;
  }

  function toggleMulti() {
    multiOnly = !multiOnly;
    page = 1;
  }

  const multiCount = $derived(rows.filter((row) => row.courses >= 2).length);

  function ariaSort(key) {
    return ariaSortFor(key, sortKey, sortDir);
  }

  const visible = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      if (multiOnly && row.courses < 2) return false;
      if (!needle) return true;
      return `${row.name ?? ''} ${row.role ?? ''} ${row.department ?? ''} ${row.page}`
        .toLowerCase()
        .includes(needle);
    });
    return [...filtered].sort(compare);
  });

  const paging = $derived(paginate(visible, page, pageSize));
  const pageCount = $derived(paging.pageCount);
  const current = $derived(paging.current);
  const shown = $derived(paging.visible);
  const first = $derived(paging.first);
  const last = $derived(paging.last);
</script>

<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
  <div class="flex flex-wrap items-center gap-2">
    <button
      class="btn btn-sm whitespace-nowrap {multiOnly ? 'btn-neutral' : 'btn-ghost'}"
      aria-pressed={multiOnly}
      onclick={toggleMulti}
    >
      Two or more courses{#if multiCount} <span class="opacity-50">{multiCount}</span>{/if}
    </button>

  </div>
  <div class="flex items-center gap-3">
    <input
      class="input input-sm w-full sm:w-64"
      value={query}
      oninput={search}
      placeholder="Filter by name or department…"
      aria-label="Filter teachers"
    />
  </div>
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
      {#each shown as row (row.page)}
        <tr>
          <td>
            <div class="flex items-center gap-3">
              <span
                class="relative inline-flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-base-300 text-[0.65rem] font-semibold text-base-content/70"
                aria-hidden="true"
              >
                {initials(row.name)}
                {#if row.photo}
                  <img
                    src={row.photo}
                    alt=""
                    class="absolute inset-0 h-full w-full object-cover"
                    loading="lazy"
                    decoding="async"
                    referrerpolicy="no-referrer"
                    onerror={(event) => event.currentTarget.remove()}
                  />
                {/if}
              </span>
              <div class="min-w-0">
                <div class="truncate font-medium">
                  <a class="link link-hover" href={`/instructors/${row.page}`}>
                    {row.name ?? row.page}
                  </a>
                </div>
                <div class="truncate text-xs text-base-content/50">
                  {row.role ?? 'Instructor'}{row.department ? ` · ${row.department}` : ''}
                </div>
              </div>
            </div>
          </td>
          <td class="text-right font-mono text-sm">{row.courses}</td>
          <td class="text-right">
            <div class="flex items-center justify-end gap-2">
              <span class="font-bold">{row.average.toFixed(1)}</span>
              <span class="hidden md:inline-flex"><Stars value={row.average} /></span>
            </div>
          </td>
          <td class="hidden text-right font-mono text-sm sm:table-cell">
            {row.low.toFixed(1)}
          </td>
          <td class="hidden text-right font-mono text-sm sm:table-cell">
            {row.high.toFixed(1)}
          </td>
          <td class="hidden text-right font-mono text-sm sm:table-cell">{row.reviews}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  {#if visible.length === 0}
    <p class="py-8 text-center text-sm text-base-content/60">No teacher matches that filter.</p>
  {:else}
    <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-base-content/60" aria-live="polite">
        Showing {first}–{last} of {visible.length}{multiOnly ? ` (${rows.length} total)` : ''}
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
