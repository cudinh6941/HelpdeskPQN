import React from "react";

export default function RootTemplate({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="anim-page-enter min-h-dvh flex flex-col">
      {children}
    </div>
  );
}
