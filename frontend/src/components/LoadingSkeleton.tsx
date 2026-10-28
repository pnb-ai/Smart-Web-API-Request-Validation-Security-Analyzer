export function LoadingSkeleton({ label = 'Loading results' }: { label?: string }) {
  return <div className="loading-skeleton" role="status" aria-label={label} aria-busy="true"><span className="skeleton skeleton-line wide"/><span className="skeleton skeleton-line"/><span className="skeleton skeleton-line short"/></div>
}
