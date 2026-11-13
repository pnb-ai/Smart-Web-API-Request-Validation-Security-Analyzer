export type SelfLoopGeometry = {
  path: string
  labelX: number
  labelY: number
}

/** Build an arch above the node from its right handle back to its left handle. */
export function getSelfLoopGeometry(sourceX: number, sourceY: number, targetX: number, targetY: number, parallelIndex = 0): SelfLoopGeometry {
  const centerX = (sourceX + targetX) / 2
  const centerY = (sourceY + targetY) / 2
  const controlY = centerY - 150 - parallelIndex * 20

  return {
    path: `M ${sourceX} ${sourceY} C ${sourceX + 4} ${controlY}, ${targetX - 4} ${controlY}, ${targetX} ${targetY}`,
    labelX: centerX,
    labelY: controlY + 37,
  }
}
