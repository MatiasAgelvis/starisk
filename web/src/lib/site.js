// The public origin of the site, in one place.
//
// Canonical URLs, Open Graph and the request feed all need an absolute base, and
// a wrong one is invisible until someone shares a link. `SITE_URL` overrides it
// at build time — useful for a preview deploy, where canonical URLs should point
// at the deployment rather than at production.
export const DEFAULT_SITE = 'https://starisk.matiasagelvis.com';
