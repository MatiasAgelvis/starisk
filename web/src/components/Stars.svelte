<script>
  import { STAR_SLOTS, clampValue, starPercent } from '../lib/stars.js';

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
    <span class="absolute inset-0 flex gap-0.5 text-base-content/25" style={`font-size:${size}px`}>
      {#each STAR_SLOTS as slot (slot)}
        <svg class="star-glyph star-glyph--outline"><use href="#star" /></svg>
      {/each}
    </span>
    <span
      class="absolute inset-0 flex gap-0.5 overflow-hidden text-warning"
      style={`width:${percent}%;font-size:${size}px`}
    >
      {#each STAR_SLOTS as slot (slot)}
        <svg class="star-glyph star-glyph--filled"><use href="#star" /></svg>
      {/each}
    </span>
  </span>
</span>
