// Shared sorting and pagination for the two tables. The components own their
// rows and labels; these helpers own the mechanics, so both behave the same.

export function compareValues(a, b, direction = 'desc') {
  if (a == null && b == null) return 0;
  if (a == null) return 1; // unknown always last
  if (b == null) return -1;
  const result = typeof a === 'string' ? a.localeCompare(b) : a - b;
  return direction === 'asc' ? result : -result;
}

export function toggleSort(key, currentKey, currentDir, textKey) {
  if (key === currentKey) {
    return { key, direction: currentDir === 'asc' ? 'desc' : 'asc' };
  }
  return { key, direction: key === textKey ? 'asc' : 'desc' };
}

export function ariaSortFor(key, sortKey, sortDir) {
  if (sortKey !== key) return 'none';
  return sortDir === 'asc' ? 'ascending' : 'descending';
}

export function paginate(rows, page, pageSize) {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pageCount);
  const start = (current - 1) * pageSize;
  return {
    pageCount,
    current,
    visible: rows.slice(start, start + pageSize),
    first: rows.length === 0 ? 0 : start + 1,
    last: Math.min(start + pageSize, rows.length),
  };
}
