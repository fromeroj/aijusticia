"use client";

/**
 * Markdown — renderer compartido para todo el sitio.
 * Usado por IzelPanel (Studio) y MessageBubble (chat ciudadano).
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="mt-3 mb-2 text-base font-bold text-foreground">{children}</h1>,
        h2: ({ children }) => <h2 className="mt-3 mb-1.5 text-sm font-bold text-foreground">{children}</h2>,
        h3: ({ children }) => <h3 className="mt-2 mb-1 text-[13px] font-semibold text-foreground">{children}</h3>,
        p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="my-1.5 ml-4 list-disc space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="my-1.5 ml-4 list-decimal space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="text-[13px]">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-primary/30 pl-3 text-muted-foreground">{children}</blockquote>
        ),
        code: ({ children, className }) => {
          if (className?.includes("language-")) {
            return (
              <code className="my-2 block overflow-x-auto rounded-lg bg-muted p-3 text-[12px] font-mono text-foreground">
                {children}
              </code>
            );
          }
          return <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12px]">{children}</code>;
        },
        pre: ({ children }) => <pre className="overflow-x-auto">{children}</pre>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-[12px]">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border-b border-border bg-muted px-2.5 py-1.5 text-left font-semibold text-foreground">{children}</th>
        ),
        td: ({ children }) => (
          <td className="border-b border-border/50 px-2.5 py-1.5 text-foreground">{children}</td>
        ),
        hr: () => <hr className="my-3 border-border" />,
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener" className="text-primary underline hover:no-underline">{children}</a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
