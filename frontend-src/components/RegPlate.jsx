// A UK registration-plate badge — yellow plate in the official "Charles Wright"
// typeface. Shared so every plate renders at an identical size, regardless of
// where it sits (table cell, card, detail field). Renders nothing when empty.
export default function RegPlate({ reg }) {
  if (!reg) return null;
  return <span className="reg-plate">{reg}</span>;
}
