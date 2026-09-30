/**
 * useTokenPricing：可编辑单价（仅 localStorage，不打后端）。
 */
const KEY = "billing.token_price.v1";

export type TokenPrice = {
  /** 每 1K input token 价格 */
  inputPer1k: number;
  /** 每 1K output token 价格 */
  outputPer1k: number;
};

const DEFAULT: TokenPrice = { inputPer1k: 0.001, outputPer1k: 0.002 };

export function loadTokenPrice(): TokenPrice {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT };
    return { ...DEFAULT, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT };
  }
}

export function saveTokenPrice(p: TokenPrice): void {
  localStorage.setItem(KEY, JSON.stringify(p));
}

/** 费用 = in/1000*单价 + out/1000*单价 */
export function estimateCost(
  tokensIn: number,
  tokensOut: number,
  price: TokenPrice,
): number {
  return (tokensIn / 1000) * price.inputPer1k + (tokensOut / 1000) * price.outputPer1k;
}
