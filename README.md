# GitHub Actions 发布测试

这是发布流程试验。示例只读取提交里的 `index.html` 文件，不执行工作分支里的代码，也没有商品、订单或生产配置。

## 运营验收

1. 从 `main` 新建 `content/first-preview`，改动并提交 `index.html`。
2. 在 **Actions → Vercel test site** 打开对应运行。Summary 会显示预览地址和以 `dpl_` 开头的编号。
3. 查看预览后，在该工作流点击 **Run workflow**，保留 `main`，填入该预览编号。Summary 会显示测试站发布地址。发布使用该预览的原始文件，不读取分支上的新提交。

## 发布凭据

GitHub Environment `vercel-lab` 的部署分支应仅允许 `main`。为 `main` 启用规则，只有仓库所有者能更新部署代码。先确认两项规则确实生效，再让运营加入仓库。个人私有仓库需要 GitHub Pro 才能使用这些规则。

由仓库所有者将限定在测试部署范围的 Vercel 凭据放入该 Environment 的 `VERCEL_LAB_TOKEN`。这是工作流访问 Vercel 的凭据。生产团队凭据和站点环境变量留在原有系统。

Vercel 官方的 [Create an Auth Token](https://vercel.com/docs/rest-api/authentication/create-an-auth-token) 提供 projectId 参数。测试只接受限制在 liebian-actions-lab 的短期部署凭据。
测试项目保留 Vercel 登录保护。和运营做验收时，由项目所有者对该预览开启定向共享。
