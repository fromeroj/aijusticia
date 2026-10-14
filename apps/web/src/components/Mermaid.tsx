"use client";

import { useEffect, useRef, useState } from "react";

export function Mermaid({ chart, className = "" }: { chart: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");

  useEffect(() => {
    let alive = true;
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        themeVariables: {
          primaryColor: "#ecfdf5",
          primaryTextColor: "#1f2937",
          primaryBorderColor: "#047857",
          lineColor: "#047857",
          fontSize: "13px",
          fontFamily: "-apple-system, sans-serif",
        },
      });
      try {
        const { svg } = await mermaid.render(`m${Math.random().toString(36).slice(2)}`, chart);
        if (alive) setSvg(svg);
      } catch {
        /* diagrama inválido — no renderizar */
      }
    })();
    return () => { alive = false; };
  }, [chart]);

  return (
    <div
      ref={ref}
      className={`mermaid-wrap overflow-x-auto [&_svg]:mx-auto [&_svg]:max-w-full ${className}`}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
