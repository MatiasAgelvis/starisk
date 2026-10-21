<script>
  import { STAR_PATH, STAR_SLOTS, clampValue, starPercent } from '../lib/stars.js';

  let { value = 0, size = 14 } = $props();

  let clamped = $derived(clampValue(value));
  let percent = $derived(starPercent(value));
  let width = $derived(size * 5 + 2 * 4);
</script>

<span
  class="inline-flex items-center"
  role="img"
  aria-label={`${clamped.toFixed(1)} out of 5 stars`}
>
  <span class="relative inline-block" style={`width:${width}px;height:${size}px`}>
    <span class="absolute inset-0 flex gap-0.5 text-base-content/25">
      {#each STAR_SLOTS as slot (slot)}
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="shrink-0"
        >
          <path d={STAR_PATH} />
        </svg>
      {/each}
    </span>
    <span
      class="absolute inset-0 flex gap-0.5 overflow-hidden text-warning"
      style={`width:${percent}%`}
    >
      {#each STAR_SLOTS as slot (slot)}
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill="currentColor"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="shrink-0"
        >
          <path d={STAR_PATH} />
        </svg>
      {/each}
    </span>
  </span>
</span>
