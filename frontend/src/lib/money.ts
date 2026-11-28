import Decimal from 'decimal.js';

export type MoneyInput = string | number | Decimal | null | undefined;

/**
 * Safely parse a monetary value into a Decimal without using JS Number/parseFloat.
 * Returns Decimal(0) for empty or invalid inputs.
 */
export function parseMoney(val: MoneyInput): Decimal {
  if (val === null || val === undefined || val === '') {
    return new Decimal(0);
  }
  if (val instanceof Decimal) {
    return val;
  }
  try {
    const cleaned = typeof val === 'string' ? val.trim() : val;
    if (cleaned === '') {
      return new Decimal(0);
    }
    return new Decimal(cleaned);
  } catch {
    return new Decimal(0);
  }
}

/**
 * Safely parse a quantity value (supporting 3 decimal places like kg/liters).
 */
export function parseQuantity(val: MoneyInput): Decimal {
  return parseMoney(val).toDecimalPlaces(3, Decimal.ROUND_HALF_UP);
}

/**
 * Format a Decimal/string/number as Sri Lankan Rupees, e.g. "Rs. 1,250.00".
 */
export function formatLKR(val: MoneyInput): string {
  const dec = parseMoney(val).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
  const isNeg = dec.isNegative();
  const fixed = dec.abs().toFixed(2);
  const [intPart, decPart] = fixed.split('.');
  const withCommas = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${isNeg ? '-' : ''}Rs. ${withCommas}.${decPart}`;
}

/**
 * Format a monetary Decimal as plain "0.00" string for API payloads.
 */
export function formatMoneyFixed(val: MoneyInput): string {
  return parseMoney(val).toDecimalPlaces(2, Decimal.ROUND_HALF_UP).toFixed(2);
}

/**
 * Format a quantity Decimal as "0.000" string for API payloads.
 */
export function formatQuantityFixed(val: MoneyInput): string {
  return parseMoney(val).toDecimalPlaces(3, Decimal.ROUND_HALF_UP).toFixed(3);
}

/**
 * Sum an array of monetary values using exact Decimal math.
 */
export function sumMoney(values: MoneyInput[]): Decimal {
  return values
    .reduce<Decimal>((acc, item) => acc.plus(parseMoney(item)), new Decimal(0))
    .toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
}

/**
 * Multiply two values (e.g. unit_price * quantity) and round HALF_UP to 2 decimals.
 */
export function multiplyMoney(a: MoneyInput, b: MoneyInput): Decimal {
  return parseMoney(a)
    .times(parseMoney(b))
    .toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
}

/**
 * Subtract b from a (a - b) and round HALF_UP to 2 decimals.
 */
export function subtractMoney(a: MoneyInput, b: MoneyInput): Decimal {
  return parseMoney(a)
    .minus(parseMoney(b))
    .toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
}
