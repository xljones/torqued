function Line({ width, height = 14 }) {
  return <div className="skeleton-line" style={{ width, height }} />;
}

const FIELD_WIDTHS = ['55%', '70%', '45%', '80%', '60%', '40%', '65%', '50%'];

export function SkeletonRows({ cols, rows = 5 }) {
  return Array.from({ length: rows }, (_, i) => (
    <tr key={i}>
      {cols.map((w, j) => (
        <td key={j}>{w && <Line width={w} />}</td>
      ))}
    </tr>
  ));
}

export function SkeletonPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <Line width={80} height={12} />
          <div style={{ marginTop: 8 }}><Line width={200} height={26} /></div>
        </div>
      </div>
      <div className="card card-body mb-4">
        <div className="form-grid">
          {FIELD_WIDTHS.map((w, i) => (
            <div className="field" key={i}>
              <Line width={60} height={11} />
              <Line width={w} height={16} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
