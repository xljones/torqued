import { formatReg, regPlateType } from '../units';

// A UK registration-plate badge — yellow plate in the official "Charles Wright"
// typeface. Shared so every plate renders at an identical size, regardless of
// where it sits (table cell, card, detail field). Renders nothing when empty.
// Plates are shown uppercase with canonical UK spacing (see formatReg), whatever
// case/spacing the value was stored in. Hovering reveals the shared [data-tooltip]
// bubble with the value exactly as stored plus the detected plate era (e.g. dateless,
// current style).
export default function RegPlate({ reg }) {
  if (!reg) return null;
  const tooltip = `Stored as ${reg} · ${regPlateType(reg)}`;
  return <span className="reg-plate" data-tooltip={tooltip}>{formatReg(reg)}</span>;
}
