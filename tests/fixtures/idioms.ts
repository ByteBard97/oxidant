export class Example {
  items: number[];
  name: string | null;

  constructor() {
    this.items = [];
    this.name = null;
  }

  // optional chaining
  getFirstItem(): number | undefined {
    return this.items?.[0];
  }

  // null coalescing (null/undefined duality)
  getName(): string {
    return this.name ?? "default";
  }

  // array method chain
  getDoubled(): number[] {
    return this.items.map(x => x * 2).filter(x => x > 0);
  }

  // closure capturing outer scope
  makeAdder(n: number): (x: number) => number {
    return (x) => x + n;
  }

  // Map usage
  buildIndex(): Map<string, number> {
    const m = new Map<string, number>();
    this.items.forEach((v, i) => m.set(String(i), v));
    return m;
  }
}

// async/await
export async function fetchData(url: string): Promise<string> {
  const response = await fetch(url);
  return response.text();
}
