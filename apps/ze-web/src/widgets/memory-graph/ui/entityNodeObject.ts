import * as THREE from "three";
import SpriteText from "three-spritetext";

// Categorical palette identifying entity type — distinct from the
// success/warning/destructive state tokens, so it intentionally doesn't use them.
const ENTITY_COLORS: Record<string, string> = {
  person: "#60a5fa",
  place: "#4ade80",
  org: "#fbbf24",
  topic: "#c084fc",
};
const DEFAULT_COLOR = "#a8a8a8";

export function entityColor(entityType: string): string {
  return ENTITY_COLORS[entityType] ?? DEFAULT_COLOR;
}

export function entityRadius(degree: number): number {
  return Math.min(10, Math.max(4, 4 + degree * 0.4));
}

export interface GraphNodeDatum {
  id: string;
  canonical_name: string;
  entity_type: string;
  degree: number;
  highlighted?: boolean;
  dimmed?: boolean;
}

export function buildEntityNodeObject(node: GraphNodeDatum): THREE.Object3D {
  const group = new THREE.Group();
  const radius = entityRadius(node.degree);
  const color = entityColor(node.entity_type);
  const opacity = node.dimmed ? 0.15 : 1;

  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 16, 16),
    new THREE.MeshLambertMaterial({ color, transparent: true, opacity }),
  );
  group.add(sphere);

  if (node.highlighted) {
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(radius * 1.3, radius * 1.5, 32),
      new THREE.MeshBasicMaterial({ color: "#e879f9", side: THREE.DoubleSide, transparent: true, opacity: 0.9 }),
    );
    group.add(ring);
  }

  const label = node.canonical_name.length > 24 ? node.canonical_name.slice(0, 24) + "…" : node.canonical_name;
  const text = new SpriteText(label);
  text.color = node.dimmed ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.85)";
  text.textHeight = 3.2;
  text.position.set(0, radius + 4, 0);
  group.add(text);

  return group;
}
