import React from "react";

export const ChatImage: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = ({
  src,
  alt,
  ...props
}) => {
  if (!src || typeof src !== "string") {
    return (
      <img
        src={src}
        alt={alt}
        className="max-w-full h-auto rounded-lg my-2 block"
        onError={(e) => {
          e.currentTarget.style.display = "none";
        }}
        {...props}
      />
    );
  }

  return (
    <a href={src} target="_blank" rel="noopener noreferrer">
      <img
        src={src}
        alt={alt}
        className="max-w-full h-auto rounded-lg my-2 block"
        onError={(e) => {
          e.currentTarget.style.display = "none";
        }}
        {...props}
      />
    </a>
  );
};
