# 通过代理连接 GitHub 的问题排查记录

## 背景

本次操作的目标是在仓库 `slivercode/pyannote` 中发布本地分支 `docs/add-readme`，并基于该分支创建 README 文档相关的 Pull Request。

本地 README 已经写入并提交，当前阻塞点不是文件内容或 Git 提交，而是本机连接 GitHub 与 GitHub CLI 认证的问题。

## 当前仓库信息

项目路径：

```text
E:\pyannote-audio-web-ui (4)\coisy_voice\pyannote
```

远端地址：

```text
https://github.com/slivercode/pyannote.git
```

当前本地分支：

```text
docs/add-readme
```

本地 README 已经存在：

```text
README.md
```

## 原始报错

在 VS Code 源代码管理中点击发布分支时，出现如下报错：

```text
fatal: unable to access 'https://github.com/slivercode/pyannote.git/':
Failed to connect to github.com port 443 after 21053 ms:
Could not connect to server
```

这说明 Git 通过 HTTPS 直连 GitHub 的 `443` 端口失败。

## 已完成的排查

### 1. 确认 GitHub 直连失败

执行：

```powershell
Test-NetConnection github.com -Port 443
```

结果显示：

```text
TcpTestSucceeded : False
```

结论：当前网络环境下，直连 `github.com:443` 不通。

### 2. 检查本地代理端口

执行：

```powershell
Test-NetConnection 127.0.0.1 -Port 7890
```

结果显示：

```text
TcpTestSucceeded : True
```

结论：本机 `127.0.0.1:7890` 端口可用，通常对应 Clash、Clash Verge、v2rayN 等代理工具的 HTTP 代理端口。

### 3. 为当前仓库配置 Git 代理

只对当前仓库配置代理：

```powershell
git config http.proxy http://127.0.0.1:7890
git config https.proxy http://127.0.0.1:7890
```

检查配置：

```powershell
git config --get http.proxy
git config --get https.proxy
```

预期输出：

```text
http://127.0.0.1:7890
http://127.0.0.1:7890
```

注意：这里配置的是仓库级 `.git/config`，不是全局配置，不会影响其他仓库。

### 4. 切换当前仓库的 Git SSL 后端

配置代理后，Git 推送时出现过 Windows `schannel` 相关错误：

```text
schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS
```

因此只对当前仓库切换 Git SSL 后端：

```powershell
git config http.sslBackend openssl
```

检查配置：

```powershell
git config --show-origin --get-regexp "http\.proxy|https\.proxy|http\.sslBackend"
```

当前仓库应能看到类似配置：

```text
file:.git/config http.proxy http://127.0.0.1:7890
file:.git/config https.proxy http://127.0.0.1:7890
file:.git/config http.sslbackend openssl
```

## 当前主要阻塞点

代理配置后，Git 推送错误从“连不上 GitHub”变成了认证相关问题：

```text
fatal: could not read Username for 'https://github.com': No such file or directory
```

随后检查 GitHub CLI 登录状态：

```powershell
gh auth status
```

结果：

```text
You are not logged into any GitHub hosts.
```

说明 GitHub CLI 当前没有登录。

再次运行 `gh auth login` 时，又出现：

```text
failed to authenticate via web browser:
Post "https://github.com/login/device/code":
read tcp ... ->20.205.243.166:443: wsarecv:
A connection attempt failed because the connected party did not properly respond after a period of time,
or established connection failed because connected host has failed to respond.
```

结论：`gh auth login` 没有走代理，仍然在直连 GitHub，所以获取浏览器登录 device code 时失败。

## 推荐解决步骤

在 PowerShell 中执行以下命令，临时让 GitHub CLI 使用本机代理：

```powershell
cd "E:\pyannote-audio-web-ui (4)\coisy_voice\pyannote"

$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"

gh auth login
```

交互选项建议如下：

```text
Where do you use GitHub? GitHub.com
What is your preferred protocol for Git operations on this host? SSH
Upload your SSH public key to your GitHub account? C:\Users\Admin\.ssh\id_ed25519.pub
Title for your SSH key: GitHub CLI
How would you like to authenticate GitHub CLI? Login with a web browser
```

随后 GitHub CLI 应该会给出浏览器登录地址和一次性授权码。请在本机浏览器中完成 GitHub 登录和授权。

登录完成后验证：

```powershell
gh auth status
```

如果状态正常，再发布分支：

```powershell
git push -u origin docs/add-readme
```

创建 Pull Request：

```powershell
gh pr create `
  --base main `
  --head docs/add-readme `
  --title "docs: add project README" `
  --body "Add a README covering project purpose, structure, setup, API routes, scripts, outputs, and operational notes."
```

## 如果仍然失败

### 情况 1：`gh auth login` 仍然超时

确认代理软件正在运行，并确认 HTTP 代理端口是否仍然是 `7890`：

```powershell
Test-NetConnection 127.0.0.1 -Port 7890
```

如果失败，请在代理软件中查看实际 HTTP 代理端口，并把命令中的 `7890` 替换为真实端口。

### 情况 2：浏览器能打开 GitHub，但 Git/gh 不行

通常是浏览器走了系统代理，但 Git 和 GitHub CLI 没有继承代理配置。继续使用以下方式显式指定：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
```

Git 仓库级代理配置可以保留：

```powershell
git config http.proxy http://127.0.0.1:7890
git config https.proxy http://127.0.0.1:7890
```

### 情况 3：GitHub CLI 登录成功，但 `git push` 仍要求用户名

如果已选择 SSH 协议，可以把远端地址从 HTTPS 改为 SSH：

```powershell
git remote set-url origin git@github.com:slivercode/pyannote.git
git push -u origin docs/add-readme
```

修改后可检查：

```powershell
git remote -v
```

预期类似：

```text
origin  git@github.com:slivercode/pyannote.git (fetch)
origin  git@github.com:slivercode/pyannote.git (push)
```

如果继续使用 HTTPS，则需要确保 Git Credential Manager 或 GitHub CLI 已经完成 HTTPS 凭据授权。

## 安全注意事项

不要把以下内容发给别人或粘贴到聊天中：

- GitHub 密码
- Personal Access Token
- 浏览器登录 device code
- 浏览器授权链接中的一次性 code
- SSH 私钥：`C:\Users\Admin\.ssh\id_ed25519`

可以安全提供的信息通常包括：

- 报错文本
- `git remote -v` 中不含 token 的普通远端地址
- `git status --short --branch`
- `gh auth status` 的普通状态输出
- 本地代理端口是否连通的测试结果

## 最终目标

完成以下三件事：

1. GitHub CLI 登录成功。
2. 本地分支 `docs/add-readme` 成功推送到 `origin`。
3. 基于 `docs/add-readme` 向 `main` 创建 README 文档 PR。
