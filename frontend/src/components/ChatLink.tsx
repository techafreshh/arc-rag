import React from "react";

export const ChatLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = ({
  href,
  children,
  ...props
}) => {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-sky-700 underline hover:text-sky-900"
      {...props}
    >
      {children}
    </a>
  );
};
