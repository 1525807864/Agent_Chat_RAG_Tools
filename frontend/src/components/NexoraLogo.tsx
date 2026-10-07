/** Nexora 品牌标识：浏览器标签用 public/favicon.svg，页面内用本组件。 */

type NexoraLogoProps = {
  /** sm=顶栏，lg=登录页主视觉 */
  size?: "sm" | "lg";
};

export function NexoraLogo({ size = "sm" }: NexoraLogoProps) {
  const cls = size === "lg" ? "nexora-logo nexora-logo--lg" : "nexora-logo";
  return (
    <img
      className={cls}
      src="/favicon.svg"
      alt="Nexora"
      width={size === "lg" ? 88 : 40}
      height={size === "lg" ? 88 : 40}
    />
  );
}
