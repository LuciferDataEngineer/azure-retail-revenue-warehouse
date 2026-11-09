# Numeric scenarios

For editable calculations, reuse the copied `src/content/shared/NumericScenario.jsx` helper. Keep keyed field definitions outside the component, with explicit units, defaults and valid bounds; do not use mixed-type tuple arrays. The helper owns numeric input, 200 ms commits, blur/Enter and reset. Formulas and assumptions remain authored. Selection controls can keep their own state; reset them in the same action.

```jsx
import { useNumericScenario } from "../shared/NumericScenario.jsx";
import { scenarioFormatter } from "../shared/numeric-scenario.js";

const fields = {
  units: { label: "Units", initial: 100, min: 0, max: 100000, step: 1 },
  margin: { label: "Margin per unit ($)", initial: 8, min: -100, max: 100, step: 0.5 },
};
const money = scenarioFormatter({ style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function Scenario() {
  const { values, inputProps, reset, setFields } = useNumericScenario(fields);
  const total = values.units * values.margin;
  return <section aria-label="Scenario assumptions">
    <div className="scenario-inputs">
      {Object.entries(fields).map(([key, field]) => <label key={key}>
        {field.label}<input {...inputProps(key)} />
      </label>)}
    </div>
    <p><output aria-label="Scenario result">{money.format(total)}</output></p>
    <button type="button" onClick={() => setFields({ units: 200, margin: 6 })}>Volume scenario</button>
    <button type="button" onClick={reset}>Reset assumptions</button>
  </section>;
}
```

Keep controls wrapping and readouts wide enough for losses. Use `values` for both calculated text and standard chart rows so they update together. Input text changes immediately; calculations retain the last valid number while a field is empty or invalid, and blur/Enter restores it. Finite values are bounded; no rounding is applied to calculations. Defaults must be finite and inside their bounds. Changing field definitions requires a new component instance.

Use `setFields({fieldKey: numericValue})` for presets, including dropdown selections. It commits pending valid inputs and applies the supplied fields immediately with the same bounds. Do not fabricate input events; pass `inputProps(key)` directly to inputs. Reset any separately authored selection state alongside `reset()`.

`scenarioFormatter` wraps `Intl.NumberFormat`: values that display as zero have no minus sign, while meaningful losses remain negative. Explicit `signDisplay` options retain the requested sign convention. Distinct source categories must retain distinct display labels; do not merge identities just to prettify them.

Check a baseline and a meaningful change independently, plus zero/negative values where valid, clearing and blurring a field, rapid input followed by reset, and any nonnumeric selections. Add these assertions through the report's existing `--checks` hook; reuse its desktop/phone verification and screenshots.
