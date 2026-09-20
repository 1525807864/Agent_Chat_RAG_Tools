/** 工信部备案号：整站最底部居中，链到备案查询。 */
export function IcpFooter() {
  return (
    <footer className="icp-footer">
      <a
        href="https://beian.miit.gov.cn/"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span className="icp-footer-text">
            ©2026 John.Lee
        </span>
        <span>
            京ICP备2026XXXXXX号-1
        </span>
      </a>
    </footer>
  );
}
