export default function BuildInfo({ className }) {
  const sha = import.meta.env.DEV
    ? <span className="build-info-live">live<span className="build-info-dot" /></span>
    : __GIT_SHA__;
  return (
    <div className={className}>
      <span className="build-info-inner">
        <span>v{__APP_VERSION__}</span>
        <span>–</span>
        {sha}
      </span>
    </div>
  );
}
