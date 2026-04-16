export class Point {
  x: number;
  y: number;

  constructor(x: number, y: number) {
    this.x = x;
    this.y = y;
  }

  add(other: Point): Point {
    return new Point(this.x + other.x, this.y + other.y);
  }

  scale(factor: number): Point {
    return new Point(this.x * factor, this.y * factor);
  }

  isZero(): boolean {
    return this.x === 0 && this.y === 0;
  }
}

export interface Shape {
  area(): number;
  perimeter(): number;
}

export enum Color {
  Red = "RED",
  Green = "GREEN",
  Blue = "BLUE",
}

export function distance(a: Point, b: Point): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

export function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
