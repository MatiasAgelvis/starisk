'use strict';

// Rank correlation, used to check a model against a hand-made ranking.
// Spearman = Pearson correlation computed on ranks (ties get average ranks).

function averageRanks(values) {
  const order = values.map((value, index) => ({ value, index }));
  order.sort((a, b) => a.value - b.value);

  const ranks = new Array(values.length);
  let i = 0;
  while (i < order.length) {
    let j = i;
    while (j + 1 < order.length && order[j + 1].value === order[i].value) {
      j += 1;
    }
    const average = (i + j) / 2 + 1; // 1-based
    for (let k = i; k <= j; k += 1) {
      ranks[order[k].index] = average;
    }
    i = j + 1;
  }
  return ranks;
}

function spearman(xs, ys) {
  if (xs.length !== ys.length || xs.length === 0) {
    throw new Error('spearman needs two equal-length, non-empty arrays');
  }

  const rx = averageRanks(xs);
  const ry = averageRanks(ys);
  const n = rx.length;
  const meanX = rx.reduce((a, b) => a + b, 0) / n;
  const meanY = ry.reduce((a, b) => a + b, 0) / n;

  let covariance = 0;
  let varianceX = 0;
  let varianceY = 0;
  for (let i = 0; i < n; i += 1) {
    covariance += (rx[i] - meanX) * (ry[i] - meanY);
    varianceX += (rx[i] - meanX) ** 2;
    varianceY += (ry[i] - meanY) ** 2;
  }

  return covariance / Math.sqrt(varianceX * varianceY);
}

module.exports = { averageRanks, spearman };
