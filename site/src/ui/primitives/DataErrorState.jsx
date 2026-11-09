import React, { useLayoutEffect, useRef } from "react";
import { DATA_STATUS_CSS, createDataStatus } from "./data-status.js";

export function DataErrorState({ error, surface = "dashboard", stage = "render", height = 240, tag: Tag = "div" }) {
  const root = useRef(null);
  useLayoutEffect(() => {
    const version = root.current.ownerDocument.querySelector('meta[name="data-plugin-version"]')?.content;
    createDataStatus(root.current, { version, surface }).fail(error, stage);
  }, [error, surface, stage]);
  return <Tag ref={root} style={{ minHeight: height }}><style>{DATA_STATUS_CSS}</style></Tag>;
}
