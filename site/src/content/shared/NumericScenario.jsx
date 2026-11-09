import { useEffect, useRef, useState } from "react";
import { scenarioDefaults, scenarioValue } from "./numeric-scenario.js";

/** Keep field definitions outside the component; formulas use committed values.
 * @param {Record<string, import('./numeric-scenario.js').NumericField>} fields
 */
export function useNumericScenario(fields) {
  const [values, setValues] = useState(() => scenarioDefaults(fields));
  const [draft, setDraft] = useState(() => Object.fromEntries(Object.entries(values).map(([key, value]) => [key, String(value)])));
  const latest = useRef(draft);
  const timer = useRef(/** @type {ReturnType<typeof setTimeout> | undefined} */ (undefined));
  useEffect(() => () => clearTimeout(timer.current), []);

  function commit(normalize = false) {
    clearTimeout(timer.current);
    setValues(previous => Object.fromEntries(Object.entries(fields).map(([key, field]) =>
      [key, scenarioValue(latest.current[key], field, previous[key])])));
    if (normalize) {
      const next = Object.fromEntries(Object.entries(fields).map(([key, field]) =>
        [key, String(scenarioValue(latest.current[key], field, values[key]))]));
      latest.current = next;
      setDraft(next);
    }
  }

  function reset() {
    clearTimeout(timer.current);
    const defaults = scenarioDefaults(fields);
    const next = Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, String(value)]));
    latest.current = next;
    setDraft(next);
    setValues(defaults);
  }

  /** Apply a numeric preset without manufacturing input events.
   * @param {Record<string, number>} patch
   */
  function setFields(patch) {
    for (const [key, value] of Object.entries(patch)) {
      if (!fields[key] || !Number.isFinite(value)) throw new Error(`Invalid numeric scenario preset: ${key}`);
    }
    latest.current = { ...latest.current, ...Object.fromEntries(Object.entries(patch).map(([key, value]) => [key, String(value)])) };
    commit(true);
  }

  /** @param {string} key @returns {import('react').InputHTMLAttributes<HTMLInputElement>} */
  function inputProps(key) {
    const field = fields[key];
    if (!field) throw new Error(`Unknown numeric scenario field: ${key}`);
    return {
      type: "number", "aria-label": field.label, min: field.min, max: field.max, step: field.step,
      value: draft[key],
      onChange(event) {
        const next = { ...latest.current, [key]: event.currentTarget.value };
        latest.current = next;
        setDraft(next);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => commit(), 200);
      },
      onBlur() { commit(true); },
      onKeyDown(event) { if (event.key === "Enter") commit(true); },
    };
  }

  return { values, inputProps, reset, setFields };
}
