import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";

const previewComponents: Components = {
  p: ({ children }) => <span className="inline">{children}</span>,
  strong: ({ children }) => <strong className="font-medium text-white/80">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
  ),
  pre: ({ children }) => <span className="inline">{children}</span>,
  ul: ({ children }) => <span className="inline">{children}</span>,
  ol: ({ children }) => <span className="inline">{children}</span>,
  li: ({ children }) => <span className="inline">{children} </span>,
  h1: ({ children }) => <span className="font-medium text-white/80">{children} </span>,
  h2: ({ children }) => <span className="font-medium text-white/80">{children} </span>,
  h3: ({ children }) => <span className="font-medium text-white/80">{children} </span>,
  blockquote: ({ children }) => <span className="inline">{children}</span>,
  a: ({ children }) => <span className="underline decoration-white/20">{children}</span>,
};

interface MarkdownPreviewProps {
  children: string;
  className?: string;
}

export function MarkdownPreview({ children, className }: MarkdownPreviewProps) {
  return (
    <ReactMarkdown className={className} components={previewComponents}>
      {children}
    </ReactMarkdown>
  );
}
