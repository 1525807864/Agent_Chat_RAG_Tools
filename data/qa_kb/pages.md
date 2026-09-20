# 被测站点页面说明（每个客户一份）

构建知识库时把本目录上传，租户 id 填 `qa-客户名`，对话里 `qa_tenant_id` 与之相同。

## 登录 https://dev.ai-training.platform.ceba.ceshiren.com/v2/user/login

- 页面是 SPA，先等表单出现，不要一打开就填
- 用户：getByPlaceholder('请输入 用户')（不是「用户名」）
- 密码：getByPlaceholder('请输入密码')
- 提交：getByRole('button', { name: '登录', exact: true })（不要点 SSO登录）
- 成功：跳到 /v2/projects，可见按钮「项目新增」
- 账号：E2E_USER / E2E_PASSWORD，不要写进脚本

换网站就换这份文档，并换 `e2e_base_url`。
