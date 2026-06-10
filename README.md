# 冲上云霄 (vpnpn.com) 每日自动签到

使用 Playwright + ddddocr 实现冲上云霄网站的每日自动签到。

## 功能

- ✅ 自动登录
- ✅ 自动识别验证码（文字/数字验证码 OCR）
- ✅ 自动签到
- ✅ 支持 GitHub Actions 自动化（每日随机时间运行）
- ✅ 支持本地运行调试

## 本地运行

### 前置条件

- Python 3.10+
- 安装依赖：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 配置凭据

将 `.env.example` 复制为 `.env` 并填入真实账号：

```bash
cp .env.example .env
# 编辑 .env 文件：
# VPNPN_USERNAME=your_username
# VPNPN_PASSWORD=your_password
```

### 运行

```bash
# 有头模式（可以看到浏览器窗口，方便调试）
python checkin.py

# 无头模式（后台静默运行）
python checkin.py --headless

# 输出结果到文件
python checkin.py --headless --result-file result.json
```

## GitHub Actions 自动化

### 部署步骤

1. 将本仓库推送到 GitHub

2. 在 GitHub 仓库的 Settings → Secrets and variables → Actions 中添加以下 Secrets：

   | Secret | 说明 |
   |--------|------|
   | `VPNPN_USERNAME` | 你的登录用户名 |
   | `VPNPN_PASSWORD` | 你的登录密码 |

3. 进入 Actions 页面，启用工作流

工作流将在每天 **北京时间 8:00-10:00 之间随机时间** 自动运行签到。

也可以手动触发运行（用于测试）：在 GitHub Actions 页面点击 "Run workflow"。

## 签到结果

签到结果会以 Action 的 Artifact 形式保存，并在 Workflow 的 Summary 中展示。

| 状态 | 说明 |
|------|------|
| `ok` | 签到成功 |
| `already_signed` | 今日已签到 |
| `captcha_failed` | 验证码识别失败 |
| `error` | 执行异常 |

## 项目结构

```
├── checkin.py              # 主签到脚本
├── requirements.txt        # Python 依赖
├── .env.example            # 凭据模板
├── .github/workflows/
│   └── checkin.yml         # GitHub Actions 工作流
└── README.md
```
