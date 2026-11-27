<script>
  import { onMount, tick } from 'svelte';
  import ScoreTable from './ScoreTable.svelte';
  import logoTones from '../data/logo-tones.json';
  import { logoTile } from '../lib/logos.js';
  import { verdictOf, VERDICT } from '../lib/verdict.js';
  import { ariaSortFor, compareValues, paginate, toggleSort } from '../lib/table.js';
  import { typeLabel } from '../lib/groupings.js';

  let { rows = [], pageSize = 25 } = $props();

  let query = $state('');
  let type = $state('all');
  let provider = $state('all');
  // What the directory admits. A set with nothing scored has no number to compare
  // on either side, so it is noise on a comparison table — but it is a third of the
  // index, so it stays one click away rather than being dropped.
  let scope = $state('complete');
  // One drawer at a time: a 12-course program is a tall panel, and two open rows
  // would push the rest of the directory off the screen.
  let open = $state(null);
  let sortKey = $state('starisk');
  let sortDir = $state('desc');
  let page = $state(1);

  const TYPES = [
    { id: 'all', label: 'All' },
    { id: 'specialization', label: 'Specializations' },
    { id: 'professional-certificate', label: 'Professional Certificates' },
  ];

  // Narrowest to widest, so the counts read as cumulative.
  const SCOPES = {
    complete: { label: 'Complete sets', test: (row) => row.complete },
    scored: { label: 'At least one score', test: (row) => row.scored > 0 },
    all: { label: 'All programs', test: () => true },
  };

  // The same three columns as the leaderboard: Coursera's number, ours, and the
  // badge that names the distance between them. Ours is the review-weighted
  // average of the courses inside; Coursera's is the pooled rating it shows for
  // the bundle. Both are bundle-level, from different populations.
  const COLUMNS = [
    { key: 'title', label: 'Program', align: 'text-left', width: 'w-auto' },
    { key: 'coursera', label: 'Coursera', align: 'text-right', width: 'w-[6rem]', hide: true },
    { key: 'starisk', label: 'Starisk', align: 'text-right', width: 'w-[6rem]', hint: 'avg' },
    { key: 'gap', label: 'Gap', align: 'text-left', width: 'w-[7rem]' },
  ];

  // Every order the dropdown offers. Column headers are shortcuts into the same
  // keys, so the select always shows the current order.
  const SORTS = [
    { value: 'starisk:desc', label: 'Score: high → low' },
    { value: 'starisk:asc', label: 'Score: low → high' },
    { value: 'coursera:desc', label: 'Coursera: high → low' },
    { value: 'coursera:asc', label: 'Coursera: low → high' },
    { value: 'gap:desc', label: 'Gap: biggest first' },
    { value: 'gap:asc', label: 'Gap: smallest first' },
    { value: 'total:desc', label: 'Most courses' },
    { value: 'total:asc', label: 'Fewest courses' },
    { value: 'title:asc', label: 'Title: A → Z' },
    { value: 'title:desc', label: 'Title: Z → A' },
  ];

  const tones = logoTones;

  function inflationOf(row) {
    return row.coursera == null || row.starisk == null ? null : row.coursera - row.starisk;
  }

  function value(row, key) {
    if (key === 'title') return (row.title ?? row.key).toLowerCase();
    if (key === 'gap') return inflationOf(row);
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

  function pickProvider(event) {
    provider = event.currentTarget.value;
    page = 1;
  }

  // The dropdown and the column headers write the same pair.
  function pickSort(event) {
    const [key, direction] = event.currentTarget.value.split(':');
    sortKey = key;
    sortDir = direction;
    page = 1;
  }

  function pickScope(event) {
    scope = event.currentTarget.value;
    page = 1;
  }

  function search(event) {
    query = event.currentTarget.value;
    page = 1;
  }

  function clearFilters() {
    query = '';
    type = 'all';
    provider = 'all';
    scope = 'complete';
    page = 1;
  }

  function ariaSort(key) {
    return ariaSortFor(key, sortKey, sortDir);
  }

  function panelId(key) {
    return `program-courses-${key.replace(/[^a-z0-9]+/gi, '-')}`;
  }

  /**
   * Opening a drawer writes the program into the hash, so a course page can link
   * straight into it (`/programs#specializations/algorithms`) and the state can be
   * shared. Closing restores the clean URL.
   */
  function toggleRow(key) {
    open = open === key ? null : key;
    const base = location.pathname + location.search;
    history.replaceState(null, '', open ? `${base}#${open}` : base);
  }

  onMount(() => {
    const reveal = async () => {
      const key = decodeURIComponent(location.hash.slice(1));
      if (!key || !rows.some((row) => row.key === key)) return;
      // A deep link wins over the default filters: the point of the link is to
      // see the courses, including when the program is partial or barely scored.
      query = '';
      type = 'all';
      scope = 'all';
      open = key;
      // The drawer may have landed on another page of the directory.
      await tick();
      const index = ordered.findIndex((row) => row.key === key);
      if (index >= 0) page = Math.floor(index / pageSize) + 1;
    };
    reveal();
    window.addEventListener('hashchange', reveal);
    return () => window.removeEventListener('hashchange', reveal);
  });

  const sortMode = $derived(`${sortKey}:${sortDir}`);
  const needle = $derived(query.trim().toLowerCase());

  /**
   * Faceted filtering, the same rule as the course table: each lane leaves its own
   * selection out, so its counts show the alternatives under the other filters.
   */
  function matches(
    row,
    { ignoreType = false, ignoreProvider = false, ignoreScope = false } = {},
  ) {
    if (!ignoreScope && !SCOPES[scope].test(row)) return false;
    if (!ignoreType && type !== 'all' && row.type !== type) return false;
    if (!ignoreProvider && provider !== 'all' && (row.provider ?? 'Unknown provider') !== provider) {
      return false;
    }
    if (!needle) return true;
    return `${row.title ?? ''} ${row.provider ?? ''} ${typeLabel(row.type)}`
      .toLowerCase()
      .includes(needle);
  }

  const scopeRows = $derived.by(() => rows.filter((row) => matches(row, { ignoreScope: true })));
  const typeRows = $derived.by(() => rows.filter((row) => matches(row, { ignoreType: true })));
  const providerRows = $derived.by(() => rows.filter((row) => matches(row, { ignoreProvider: true })));
  const filtered = $derived.by(() => rows.filter((row) => matches(row)));

  // Cumulative by construction, and scoped to the other filters so the three
  // numbers move the same way as everything else on the bar.
  const scopeCounts = $derived.by(() => {
    const counts = {};
    for (const [id, option] of Object.entries(SCOPES)) {
      counts[id] = scopeRows.filter((row) => option.test(row)).length;
    }
    return counts;
  });

  const typeCounts = $derived.by(() => {
    const counts = new Map([['all', typeRows.length]]);
    for (const row of typeRows) counts.set(row.type, (counts.get(row.type) ?? 0) + 1);
    return counts;
  });

  // Providers come from the data, ordered by coverage — the useful axis once the
  // list is longer than a screen. The selected one survives a filter that empties
  // it, so the select never renders blank.
  const providers = $derived.by(() => {
    const counts = new Map();
    for (const row of providerRows) {
      const name = row.provider ?? 'Unknown provider';
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    if (provider !== 'all' && !counts.has(provider)) counts.set(provider, 0);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
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

<div class="mb-4 flex flex-col gap-3">
  <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
    <div class="flex flex-wrap gap-2">
      {#each TYPES as option (option.id)}
        <button
          class="btn btn-sm whitespace-nowrap {type === option.id ? 'btn-neutral' : 'btn-ghost'}"
          aria-pressed={type === option.id}
          onclick={() => pickType(option.id)}
        >
          {option.label}
          <span class="opacity-50">{typeCounts.get(option.id) ?? 0}</span>
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
  <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
    <label class="flex items-center gap-1.5">
      <span class="text-[0.65rem] font-semibold uppercase tracking-wider text-base-content/40">
        Provider
      </span>
      <select
        class="select select-xs"
        value={provider}
        onchange={pickProvider}
        aria-label="Filter by provider"
      >
        <option value="all">Any</option>
        {#each providers as [name, count] (name)}
          <option value={name}>{name} ({count})</option>
        {/each}
      </select>
    </label>
    <label class="flex items-center gap-1.5">
      <span class="text-[0.65rem] font-semibold uppercase tracking-wider text-base-content/40">
        Sort
      </span>
      <select class="select select-xs" value={sortMode} onchange={pickSort} aria-label="Sort programs">
        {#each SORTS as option (option.value)}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
    </label>
    <label class="flex items-center gap-1.5 sm:ml-auto">
      <span class="text-[0.65rem] font-semibold uppercase tracking-wider text-base-content/40">
        Show
      </span>
      <select
        class="select select-xs"
        value={scope}
        onchange={pickScope}
        aria-label="Which programs to list"
      >
        {#each Object.entries(SCOPES) as [id, option] (id)}
          <option value={id}>{option.label} ({scopeCounts[id] ?? 0})</option>
        {/each}
      </select>
    </label>
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
              {#if column.hint}
                <span class="text-[0.6rem] font-normal text-base-content/40">{column.hint}</span>
              {/if}
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
        {@const comparable = row.complete &&
          row.coursera != null &&
          typeof row.starisk === 'number'}
        {@const style = comparable ? VERDICT[verdictOf(row.coursera, row.starisk)] : null}
        {@const isOpen = open === row.key}
        {@const id = panelId(row.key)}
        {@const logoSrc = logoTile(row.image) ?? '/coursera-logo.png'}
        {@const darkChip = tones[logoSrc] === 'dark'}
        <tr class="cursor-pointer" onclick={() => toggleRow(row.key)}>
          <td>
            <div class="flex items-center gap-3">
              <button
                class="btn btn-ghost btn-xs btn-square shrink-0"
                aria-expanded={isOpen}
                aria-controls={isOpen ? id : null}
                aria-label={`${isOpen ? 'Hide' : 'Show'} the courses in ${row.title}`}
                onclick={(event) => {
                  event.stopPropagation();
                  toggleRow(row.key);
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
                class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded p-1 ring-1 {darkChip
                  ? 'bg-base-content ring-base-content/20'
                  : 'bg-white ring-base-300/60'}"
              >
                <img
                  src={logoSrc}
                  alt=""
                  class="h-full w-full object-contain drop-shadow-[0_0_1px_rgba(0,0,0,0.6)]"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                />
              </span>
              <div class="min-w-0">
                <div class="truncate font-medium">
                  <a
                    class="link link-hover"
                    href={`/programs/${row.key}`}
                    onclick={(event) => event.stopPropagation()}>{row.title}</a
                  >
                </div>
                <div class="flex items-center gap-2 text-xs text-base-content/50">
                  <span class="min-w-0 truncate">
                    {row.provider ?? 'Unknown provider'}{' · '}{row.total}{' '}
                    {row.total === 1 ? 'course' : 'courses'}
                  </span>
                  {#if !row.complete}
                    <!-- The same badge at any level of coverage: a program with none
                         scored is the most incomplete one, not a quieter case. -->
                    <span class="badge badge-warning badge-sm shrink-0 whitespace-nowrap">
                      Incomplete {row.scored}/{row.total}
                    </span>
                  {/if}
                </div>
              </div>
            </div>
          </td>
          <td class="hidden text-right sm:table-cell">
            {row.coursera == null ? '—' : row.coursera.toFixed(1)}
          </td>
          <td class="text-right">
            {#if typeof row.starisk === 'number'}
              <span class="font-bold">{row.starisk.toFixed(1)}</span>
            {:else}
              <span class="badge badge-ghost badge-sm whitespace-nowrap">No score</span>
            {/if}
          </td>
          <td>
            {#if style}
              <span class="badge whitespace-nowrap {style.badge}">{style.label}</span>
            {:else}
              <span class="text-base-content/30" title="Only complete sets are compared">—</span>
            {/if}
          </td>
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
                <div class="mb-2 space-y-1 px-3 text-xs text-base-content/60 sm:px-4">
                  <p>
                    {row.scored} of {row.total} courses scored{#if row.unread}{` · ${row.unread} not read yet`}{/if}{#if row.noReviews}{` · ${row.noReviews} with no written reviews`}{/if}{` · ${row.reviews} reviews read`}{#if row.coursera != null && row.ratings != null}{` · Coursera ${row.coursera.toFixed(1)} from ${row.ratings.toLocaleString()} ratings`}{/if}
                  </p>
                  {#if row.instructors.length > 0}
                    <p>
                      Taught by{' '}{#each row.instructors as person, index (person.page)}{#if index > 0}{', '}{/if}<a
                          class="link link-hover"
                          href={`/instructors/${person.page}`}>{person.name}</a
                        >{/each}{#if row.instructorCount > row.instructors.length}{` +${row.instructorCount - row.instructors.length} more`}{/if}
                    </p>
                  {/if}
                </div>
                {#if row.courses.some((course) => course.read)}
                  <ScoreTable
                    rows={row.courses.filter((course) => course.read)}
                    showFilters={false}
                    compact={true}
                    defaultSortKey="starisk"
                  />
                {:else}
                  <p class="px-3 pb-2 text-xs text-base-content/60 sm:px-4">
                    None of these courses is read yet.
                  </p>
                {/if}
              </div>
            </td>
          </tr>
        {/if}
      {/each}
    </tbody>
  </table>

  {#if ordered.length === 0}
    <div class="py-10 text-center text-sm text-base-content/60">
      <p>
        {scope === 'complete'
          ? 'No complete program matches those filters.'
          : 'No program matches those filters.'}
      </p>
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
