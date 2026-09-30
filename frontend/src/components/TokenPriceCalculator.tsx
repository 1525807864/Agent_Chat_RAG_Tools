/**
 * TokenPriceCalculator：可编辑单价 + 按租户累计估算费用。
 */
import { useEffect, useState } from "react";
import type { TenantUsageDTO } from "../types/api";
import {
  estimateCost,
  loadTokenPrice,
  saveTokenPrice,
  type TokenPrice,
} from "../hooks/useTokenPricing";

type Props = {
  tenantUsage?: TenantUsageDTO | null;
};

export function TokenPriceCalculator({ tenantUsage }: Props) {
  const [price, setPrice] = useState<TokenPrice>(() => loadTokenPrice());
  const [open, setOpen] = useState(false);

  useEffect(() => {
    saveTokenPrice(price);
  }, [price]);

  const tin = tenantUsage?.tokens_in ?? 0;
  const tout = tenantUsage?.tokens_out ?? 0;
  const cost = estimateCost(tin, tout, price);

  return (
    <div className="token-calc">
      <button
        type="button"
        className="token-calc-toggle"
        onClick={() => setOpen((v) => !v)}
      >
        Token 费用
      </button>
      {open ? (
        <div className="token-calc-panel">
          <label>
            输入单价 / 1K
            <input
              type="number"
              step="0.0001"
              min="0"
              value={price.inputPer1k}
              onChange={(e) =>
                setPrice((p) => ({
                  ...p,
                  inputPer1k: Number(e.target.value) || 0,
                }))
              }
            />
          </label>
          <label>
            输出单价 / 1K
            <input
              type="number"
              step="0.0001"
              min="0"
              value={price.outputPer1k}
              onChange={(e) =>
                setPrice((p) => ({
                  ...p,
                  outputPer1k: Number(e.target.value) || 0,
                }))
              }
            />
          </label>
          <p className="token-calc-sum">
            累计 in {tin} · out {tout} → 约 {cost.toFixed(4)}
          </p>
        </div>
      ) : null}
    </div>
  );
}
