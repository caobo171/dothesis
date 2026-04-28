// frontend/lib/util/timezone.ts
//
// Detect whether the current user is in a Vietnamese timezone. Used to switch
// the /credit page from international card payments to Sepay bank-transfer.
//
// We don't ship server-side geolocation — timezone is the cheapest signal
// available client-side and is correct for the common case (resident user
// browsing locally). Travelers / VPN users can still use the regular tabs;
// the page exposes both options whenever the timezone says VN.

const VN_TIMEZONES = new Set([
  // Modern IANA name. The one Chrome/Safari/Firefox return today.
  'Asia/Ho_Chi_Minh',
  // Legacy alias still emitted by some Linux distros and older OSes.
  'Asia/Saigon',
]);

export function isVietnameseTimezone(): boolean {
  if (typeof Intl === 'undefined') return false;
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return VN_TIMEZONES.has(tz);
  } catch {
    return false;
  }
}
