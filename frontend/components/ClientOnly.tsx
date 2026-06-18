"use client";
import { PropsWithChildren } from "react";

export default function ClientOnly({ children }: PropsWithChildren) {
  return <>{children}</>;
}
