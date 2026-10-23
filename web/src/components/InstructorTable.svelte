<script>
  import Stars from './Stars.svelte';
  import { initials } from '../lib/instructors.js';

  let { rows = [] } = $props();

  let query = $state('');
  let sortKey = $state('courses');
  let sortDir = $state('desc');

  // Default order is "most courses first" — a directory, not a podium. The
  // average is sortable because a visitor will want it, and pretending otherwise
  // would just be a table that fights its reader.
  const COLUMNS = [
    { key: 'name', label: 'Teacher', align: 'text-left', width: 'w-[62%] sm:w-[44%]' },
    { key: 'courses', label: 'Courses', align: 'text-right', width: 'w-[14%] sm:w-[12%]' },
    { key: 'average', label: 'Avg', align: 'text-right', width: 'w-[24%] sm:w-[16%]' },
    { key: 'low', label: 'Range', align: 'text-right', width: 'w-[14%]', hide: true },
    { key: 'reviews', label: 'Reviews read', align: 'text-right', width: 'w-[14%]', hide: true },
  ];

  function value(row, key) {
    if (key === 'name') return (row.name ?? row.page).toLowerCase();
    return row[key] ?? null;
  }

  function compare(a, b) {
    const av = value(a, sortKey);
    const bv = value(b, sortKey);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
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
    sortDir = key === 'name' ? 'asc' : 'desc';
  }

  function ariaSort(key) {
    if (sortKey !== key) return 'none';
    return sortDir === 'asc' ? 'ascending' : 'descending';
  }

  const visible = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      if (!needle) return true;
      return `${row.name ?? ''} ${row.role ?? ''} ${row.department ?? ''} ${row.page}`
        .toLowerCase()
        .includes(needle);
    });
    return [...filtered].sort(compare);
  });
</script>

<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
  <p class="text-xs text-base-content/60">
    Sorted by how many courses Starisk has scored. Sort by any column.
  </p>
  <div class="flex items-center gap-3">
    <input
      class="input input-sm w-full sm:w-64"
      bind:value={query}
      placeholder="Filter by name or department…"
      aria-label="Filter teachers"
    />
    <span class="whitespace-nowrap text-xs text-base-content/60">
      {visible.length} of {rows.length}
    </span>
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
      {#each visible as row (row.page)}
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
          <td class="hidden whitespace-nowrap text-right font-mono text-sm sm:table-cell">
            {row.low.toFixed(1)}–{row.high.toFixed(1)}
          </td>
          <td class="hidden text-right font-mono text-sm sm:table-cell">{row.reviews}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  {#if visible.length === 0}
    <p class="py-8 text-center text-sm text-base-content/60">No teacher matches that filter.</p>
  {/if}
</div>
