export const count = value => new Intl.NumberFormat('en-GB').format(value);
export const compactCount = value => new Intl.NumberFormat('en-GB', {notation:'compact', maximumFractionDigits:2}).format(value);
export const money = (value, currency = 'GBP') => new Intl.NumberFormat('en-GB', {style:'currency', currency, maximumFractionDigits:2}).format(value);
export const compactMoney = (value, currency = 'GBP') => new Intl.NumberFormat('en-GB', {style:'currency', currency, notation:'compact', maximumFractionDigits:2}).format(value);
export function cents(value) {
  const text = String(value);
  if (!/^-?\d+\.\d{2}$/.test(text)) throw new Error('Expected an exact two-decimal amount');
  const [whole, fractional] = text.replace('-', '').split('.');
  const result = (Number(whole) * 100 + Number(fractional)) * (text.startsWith('-') ? -1 : 1);
  if (!Number.isSafeInteger(result)) throw new Error('Amount exceeds safe cent range');
  return result;
}
export function sumMoney(rows, key) {
  const value = rows.reduce((total, row) => total + cents(row[key]), 0);
  if (!Number.isSafeInteger(value)) throw new Error('Total exceeds safe cent range');
  return value / 100;
}
export const sum = (rows, key) => rows.reduce((total, row) => total + row[key], 0);
