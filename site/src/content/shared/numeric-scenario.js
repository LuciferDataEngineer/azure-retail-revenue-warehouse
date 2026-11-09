/** @typedef {{label: string, initial: number, min: number, max: number, step: number}} NumericField */

/** @param {Record<string, NumericField>} fields */
export function scenarioDefaults(fields) {
  return Object.fromEntries(Object.entries(fields).map(([key, field]) => {
    if (![field.initial, field.min, field.max, field.step].every(Number.isFinite)
      || field.min > field.max || field.step <= 0 || field.initial < field.min || field.initial > field.max) {
      throw new Error(`Invalid numeric scenario field: ${key}`);
    }
    return [key, field.initial];
  }));
}

/** Empty or invalid input retains the last committed value until blur/reset.
 * @param {string} raw
 * @param {NumericField} field
 * @param {number} previous
 */
export function scenarioValue(raw, field, previous) {
  const value = raw.trim() === "" ? NaN : Number(raw);
  return Number.isFinite(value) ? Math.min(field.max, Math.max(field.min, value)) : previous;
}

/** Suppress a minus sign only when the displayed value rounds to zero.
 * @param {Intl.NumberFormatOptions} [options]
 * @param {string} [locale]
 */
export function scenarioFormatter(options = {}, locale = "en-US") {
  const formatter = new Intl.NumberFormat(locale, options);
  const zero = formatter.format(0), negativeZero = formatter.format(-0);
  return {
    /** @param {number} value */
    format(value) {
      const formatted = formatter.format(value);
      return options.signDisplay === undefined && formatted === negativeZero ? zero : formatted;
    },
  };
}
