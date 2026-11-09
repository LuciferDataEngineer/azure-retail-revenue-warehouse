# Shared primitives

`Tabs`/`TabPanel` switch local content inside a section or inspector. The default is the shared underline treatment; `variant="pills"` retains the older treatment. Use the shell's [dashboard tabs](../controls/filtering.md#tab-scope-and-exploration) for top-level views and tab-scoped filters.

`Button`, `Dialog`, `InfoTooltip`, `MenuItem`, `MenuSub`, `MenuGroup`, and `MenuSeparator` expose the existing shared primitives. `TruncatedText` reveals clipped labels after a short hover delay; component titles and dropdown/segment labels use it automatically. It preserves the full accessible text and suppresses reveal while editing.

`Dialog` defaults to a compact 480px width and shared typography; `expanded` remains available for larger workspaces. Keep it mounted with controlled `open` and `onClose` for entry/exit transitions and focus restoration. Reduced motion is respected; modal scroll/focus containment remains enabled.
