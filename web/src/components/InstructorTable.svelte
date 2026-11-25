<script>
  import Stars from './Stars.svelte';
  import ScoreTable from './ScoreTable.svelte';
  import { initials } from '../lib/instructors.js';
  import { ariaSortFor, compareValues, paginate, toggleSort } from '../lib/table.js';

  let { rows = [], pageSize = 25 } = $props();

  let query = $state('');
  let sortKey = $state('courseCount');
  let sortDir = $state('desc');
  let multiOnly = $state(false);
  // One drawer at a time. A publisher account has hundreds of courses, so the
  // drawer shows the best five and links to the page for the rest.
  let open = $state(null);
  let page = $state(1);

  // Default order is "most courses first" — a directory, not a podium. The
  // average is sortable because a visitor will want it, and pretending otherwise
  // would just be a table that fights its reader.
  const COLUMNS = [
    { key: 'name', label: 'Teacher', align: 'text-left', width: 'w-auto' },
    { key: 'courseCount', label: 'Courses', align: 'text-right', width: 'w-20' },
    { key: 'average', label: 'Avg', align: 'text-right', width: 'w-[6rem] md:w-[9.5rem]' },
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

  function toggleRow(key) {
    open = open === key ? null : key;
  }

  function panelId(key) {
    return `teacher-courses-${key.replace(/[^a-z0-9]+/gi, '-')}`;
  }

  const multiCount = $derived(rows.filter((row) => row.courseCount >= 2).length);

  function ariaSort(key) {
    return ariaSortFor(key, sortKey, sortDir);
  }

  const visible = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      if (multiOnly && row.courseCount < 2) return false;
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
        {@const isOpen = open === row.page}
        {@const id = panelId(row.page)}
        <tr class="cursor-pointer" onclick={() => toggleRow(row.page)}>
          <td>
            <div class="flex items-center gap-3">
              <button
                class="btn btn-ghost btn-xs btn-square shrink-0"
                aria-expanded={isOpen}
                aria-controls={isOpen ? id : null}
                aria-label={`${isOpen ? 'Hide' : 'Show'} the courses by ${row.name ?? row.page}`}
                onclick={(event) => {
                  event.stopPropagation();
                  toggleRow(row.page);
                }}
              >
                <svg
                  class="h-4 w-4 transition-transform {isOpen ? 'rotate-90' : ''}"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fill-rule="evenodd"
                    d="M7.21 14.77a.75.75 0 01.02-1.06L11.17 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                    clip-rule="evenodd"
                  />
                </svg>
              </button>
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
                  <a
                    class="link link-hover"
                    href={`/instructors/${row.page}`}
                    onclick={(event) => event.stopPropagation()}>{row.name ?? row.page}</a
                  >
                </div>
                <div class="truncate text-xs text-base-content/50">
                  {row.role ?? 'Instructor'}{row.department ? ` · ${row.department}` : ''}
                </div>
              </div>
            </div>
          </td>
          <td class="text-right font-mono text-sm">{row.courseCount}</td>
          <td class="text-right">
            <div class="flex items-center justify-end gap-2">
              <span class="font-bold">{row.average.toFixed(1)}</span>
              <span class="hidden md:inline-flex"><Stars value={row.average} /></span>
            </div>
          </td>
          <td class="hidden text-right font-mono text-sm sm:table-cell">{row.reviews}</td>
        </tr>
        {#if isOpen}
          <tr id={id} class="hover:bg-transparent">
            <!-- Clicks inside the drawer are for its links, not for toggling the row. -->
            <td
              colspan={COLUMNS.length}
              class="bg-base-200/50 px-0"
              onclick={(event) => event.stopPropagation()}
            >
              <div class="py-2 sm:pl-16">
                <p class="mb-2 px-3 text-xs text-base-content/60 sm:px-4">
                  {row.courseCount === 1 ? '1 course scored' : `${row.courseCount} courses scored`}{#if row.coursesTaught && row.coursesTaught > row.courseCount}{` of ${row.coursesTaught} on Coursera`}{/if}{` · ${row.reviews} reviews read`}{#if row.courseCount > row.topCourses.length}{' · best five shown'}{/if}
                </p>
                <ScoreTable
                  rows={row.topCourses}
                  showFilters={false}
                  compact={true}
                  defaultSortKey="starisk"
                />
                {#if row.courseCount > row.topCourses.length}
                  <p class="mt-2 px-3 text-xs sm:px-4">
                    <a class="link link-hover" href={`/instructors/${row.page}`}>
                      See all {row.courseCount} on {row.name ?? row.page}'s page →
                    </a>
                  </p>
                {/if}
              </div>
            </td>
          </tr>
        {/if}
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
