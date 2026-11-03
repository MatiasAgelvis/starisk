// Which provider logos are white-on-transparent?
//
// Coursera ships a few partner marks as white artwork on a transparent
// background, made for dark headers. On the site's light logo chip they simply
// vanish, and a drop-shadow only traces an outline around nothing. So: measure
// each PNG and write the exceptions to a small map the logo tiles consult.
//
// Only PNG can be inspected with the standard library, and only PNG needs to be:
// JPEG has no alpha channel, so it always brings its own background and stays
// readable on a light chip.

import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { inflateSync } from 'node:zlib';

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const CHANNELS = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  return pb <= pc ? b : c;
}

/** Decode an 8-bit, non-interlaced PNG to raw pixels. Null for anything else. */
function decode(buffer) {
  if (buffer.length < 8 || !buffer.subarray(0, 8).equals(SIGNATURE)) return null;

  const chunks = [];
  for (let offset = 8; offset + 8 <= buffer.length; ) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);
    chunks.push({ type, data: buffer.subarray(offset + 8, offset + 8 + length) });
    offset += length + 12;
    if (type === 'IEND') break;
  }

  const header = chunks.find((chunk) => chunk.type === 'IHDR')?.data;
  if (!header) return null;

  const width = header.readUInt32BE(0);
  const height = header.readUInt32BE(4);
  const depth = header[8];
  const colorType = header[9];
  const interlace = header[12];
  const channels = CHANNELS[colorType];
  if (depth !== 8 || interlace !== 0 || !channels || width === 0 || height === 0) return null;

  const palette = chunks.find((chunk) => chunk.type === 'PLTE')?.data ?? null;
  if (colorType === 3 && !palette) return null;
  // tRNS carries transparency for palette and single-colour images, where the
  // pixels themselves have no alpha channel.
  const trns = chunks.find((chunk) => chunk.type === 'tRNS')?.data ?? null;

  const compressed = chunks.filter((chunk) => chunk.type === 'IDAT').map((chunk) => chunk.data);
  if (compressed.length === 0) return null;
  const raw = inflateSync(Buffer.concat(compressed));

  const stride = width * channels;
  if (raw.length < (stride + 1) * height) return null;
  const pixels = Buffer.alloc(stride * height);
  let previous = Buffer.alloc(stride);
  let source = 0;

  for (let y = 0; y < height; y += 1) {
    const filter = raw[source];
    source += 1;
    const line = Buffer.from(raw.subarray(source, source + stride));
    source += stride;

    for (let x = 0; x < stride; x += 1) {
      const left = x >= channels ? line[x - channels] : 0;
      const up = previous[x];
      const upLeft = x >= channels ? previous[x - channels] : 0;
      if (filter === 1) line[x] = (line[x] + left) & 0xff;
      else if (filter === 2) line[x] = (line[x] + up) & 0xff;
      else if (filter === 3) line[x] = (line[x] + ((left + up) >> 1)) & 0xff;
      else if (filter === 4) line[x] = (line[x] + paeth(left, up, upLeft)) & 0xff;
    }

    line.copy(pixels, y * stride);
    previous = line;
  }

  return { channels, colorType, palette, trns, pixels };
}

/** How light are the opaque pixels, and how much of the canvas do they cover? */
function measure(image) {
  const { channels, colorType, palette, trns, pixels } = image;
  let total = 0;
  let opaque = 0;
  let luminance = 0;
  let white = 0;

  for (let i = 0; i < pixels.length; i += channels) {
    let r;
    let g;
    let b;
    let alpha = 255;

    if (colorType === 3) {
      const index = pixels[i];
      const offset = index * 3;
      r = palette[offset];
      g = palette[offset + 1];
      b = palette[offset + 2];
      if (trns && index < trns.length) alpha = trns[index];
    } else if (channels <= 2) {
      r = g = b = pixels[i];
      if (channels === 2) alpha = pixels[i + 1];
      else if (trns && trns.length >= 2 && r === trns.readUInt16BE(0)) alpha = 0;
    } else {
      r = pixels[i];
      g = pixels[i + 1];
      b = pixels[i + 2];
      if (channels === 4) alpha = pixels[i + 3];
      else if (
        trns &&
        trns.length >= 6 &&
        r === trns.readUInt16BE(0) &&
        g === trns.readUInt16BE(2) &&
        b === trns.readUInt16BE(4)
      )
        alpha = 0;
    }

    total += 1;
    if (alpha < 128) continue;
    opaque += 1;
    const l = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    luminance += l;
    if (l > 230) white += 1;
  }

  if (opaque === 0) return null;
  return {
    meanLuminance: luminance / opaque,
    whiteShare: white / opaque,
    opaqueShare: opaque / total,
  };
}

/**
 * White artwork on a transparent background is the only case that needs a dark
 * chip. An opaque image that is mostly white brings its own white field — it is
 * a wordmark on its own background, and it reads fine on the light chip.
 */
function needsDarkChip(stats) {
  return stats.meanLuminance > 235 && stats.whiteShare > 0.85 && stats.opaqueShare < 0.95;
}

/** Every file under `dir`, with a `/`-joined key relative to it (`hi/google.png`). */
function* walk(dir, prefix = '') {
  const entries = readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path, `${prefix}${entry.name}/`);
    else yield { name: entry.name, path, key: `${prefix}${entry.name}` };
  }
}

export function buildLogoTones(dir) {
  const tones = {};
  if (!existsSync(dir)) return tones;

  for (const file of walk(dir)) {
    if (!file.name.toLowerCase().endsWith('.png')) continue;
    let stats = null;
    try {
      const image = decode(readFileSync(file.path));
      if (image) stats = measure(image);
    } catch {
      // A corrupt or exotic PNG must never break the build: treat it as light.
    }
    if (stats && needsDarkChip(stats)) tones[`/logos/${file.key}`] = 'dark';
  }

  return tones;
}

function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const tones = buildLogoTones(resolve(here, '../public/logos'));
  const out = resolve(here, '../src/data/logo-tones.json');
  writeFileSync(out, `${JSON.stringify(tones, null, 2)}\n`);

  const names = Object.keys(tones).map((path) => path.replace('/logos/', ''));
  console.log(
    `[logo-tones] ${names.length} white-on-transparent logo(s)` +
      (names.length ? `: ${names.join(', ')}` : ''),
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
