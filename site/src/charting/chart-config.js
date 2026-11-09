import { checkedChartConfig, chartConfigEntries } from "./shared/config.js";
import { appChartLimits } from "./shared/limits.js";
export { chartConfigColors } from "./shared/config.js";

// App hosting has larger resource budgets; semantic validation is identical.
export const checkedAppChartConfig = config => checkedChartConfig(config, { limits: appChartLimits });
export const appChartConfigEntries = config => chartConfigEntries(config, { limits: appChartLimits });
