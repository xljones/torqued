// A UK registration-plate badge — yellow plate in the official "Charles Wright"
// typeface. Shared so every plate renders at an identical size, regardless of
// where it sits (table cell, card, detail field). Renders nothing when empty.
// Plates are always shown uppercase, whatever case the value was stored in.
export default function RegPlate({ reg }) {
  if (!reg) return null;
  return <span className="reg-plate">{String(reg).toUpperCase()}</span>;
}
