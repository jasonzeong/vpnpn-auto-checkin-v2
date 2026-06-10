#!/usr/bin/env python3
"""
冲上云霄 (vpnpn.com) 每日自动签到脚本

使用 Playwright 实现浏览器自动化 + ddddocr 验证码识别。

使用方式:
    # 本地运行（有头模式，可看到浏览器窗口）
    python checkin.py

    # 本地运行（无头模式）
    python checkin.py --headless

    # GitHub Actions 运行
    python checkin.py --headless --browser-channel chromium --result-file result.json

环境变量:
    VPNPN_USERNAME: 登录用户名
    VPNPN_PASSWORD: 登录密码
    也可通过 .env 文件加载（详见 .env.example）
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, expect

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vpnpn-checkin")

# 页面 URL 常量
LOGIN_URL = "https://my.vpnpn.com/login"
DASHBOARD_URL = "https://my.vpnpn.com/dashboard"

# 结果标记
RESULT_OK = "ok"
RESULT_ALREADY = "already_signed"
RESULT_CAPTCHA_FAILED = "captcha_failed"
RESULT_ERROR = "error"


def load_credentials():
    """加载登录凭据（优先环境变量，回退 .env 文件）"""
    load_dotenv()

    username = os.getenv("VPNPN_USERNAME")
    password = os.getenv("VPNPN_PASSWORD")

    if not username or not password:
        logger.error("缺少登录凭据！请设置 VPNPN_USERNAME 和 VPNPN_PASSWORD 环境变量或 .env 文件。")
        sys.exit(1)

    return username, password


def safe_click(page: Page, locator, timeout: int = 8000):
    """安全地等待元素出现并点击"""
    try:
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()
        page.wait_for_timeout(500)
        return True
    except Exception as e:
        logger.warning(f"点击元素失败 (timeout={timeout}ms): {e}")
        return False


def solve_captcha(page: Page) -> str | None:
    """
    识别验证码图片中的文字。
    使用 ddddocr 识别验证码图片。
    """
    ocr = None
    try:
        import ddddocr

        ocr = ddddocr.DdddOcr()

        # 等待验证码图片加载
        captcha_img = page.locator('img[alt="captcha"]')
        captcha_img.wait_for(state="visible", timeout=10000)
        page.wait_for_timeout(500)  # 确保图片渲染完成

        # 截图验证码元素
        screenshot_bytes = captcha_img.screenshot()

        # OCR 识别
        result = ocr.classification(screenshot_bytes)
        if not result or not result.strip():
            logger.warning("OCR 未能识别出验证码")
            return None

        logger.info(f"验证码识别结果: '{result}'")
        return result.strip()

    except ImportError:
        logger.error("ddddocr 未安装，请运行: pip install ddddocr")
        return None
    except Exception as e:
        logger.error(f"验证码识别异常: {e}")
        return None
    finally:
        # 清理 OCR 对象以释放 CUDA/ONNX 资源
        if ocr is not None:
            try:
                del ocr
            except Exception:
                pass


def perform_checkin(page: Page) -> str:
    """
    执行签到操作。
    返回签到结果状态码。
    """
    logger.info("===== 开始签到流程 =====")

    # --- Step 1: 导航到 Dashboard / 登录 ---
    logger.info(f"导航到 Dashboard: {DASHBOARD_URL}")
    page.goto(DASHBOARD_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 检查当前是否在登录页（未登录状态）
    current_url = page.url
    if "/login" in current_url:
        logger.info("检测到未登录，执行登录...")
        if not login(page):
            return RESULT_ERROR
    else:
        logger.info("已登录状态，继续...")

    # --- Step 2: 关闭可能的通知弹窗 ---
    dialog_btn = page.get_by_role("button", name="我知道了")
    if safe_click(page, dialog_btn, timeout=3000):
        logger.info("已关闭通知弹窗")
        page.wait_for_timeout(1000)

    # --- Step 3: 选择"专业人士"模式（如果出现） ---
    pro_mode = page.locator("text=进入专业模式").first
    if safe_click(page, pro_mode, timeout=3000):
        logger.info("已选择专业模式")
        page.wait_for_timeout(1500)

    # --- Step 4: 关闭可能再次出现的通知弹窗 ---
    # 使用 force=True 避免被父级元素拦截点击
    try:
        dialog_btn = page.get_by_role("button", name="我知道了")
        if dialog_btn.is_visible(timeout=1000):
            dialog_btn.click(force=True, timeout=2000)
            logger.info("已关闭第二个通知弹窗")
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # --- Step 5: 点击"每日签到"入口 ---
    logger.info("寻找签到入口...")
    checkin_entry = page.locator("text=每日签到").first
    if not safe_click(page, checkin_entry, timeout=5000):
        logger.error("找不到签到入口元素")
        return RESULT_ERROR
    logger.info("已点击每日签到，等待签到弹窗...")
    page.wait_for_timeout(1500)

    # --- Step 6: 处理验证码 ---
    logger.info("识别验证码...")
    captcha_text = solve_captcha(page)
    if not captcha_text:
        # 重试一次（点击验证码图片刷新，再试一次）
        logger.warning("验证码第一次识别失败，尝试刷新验证码后重试...")
        captcha_img = page.locator('img[alt="captcha"]')
        if captcha_img.is_visible():
            captcha_img.click()
            page.wait_for_timeout(1000)
        captcha_text = solve_captcha(page)

    if not captcha_text:
        logger.error("验证码识别失败（已重试）")
        return RESULT_CAPTCHA_FAILED

    # --- Step 7: 输入验证码 ---
    logger.info(f"输入验证码: {captcha_text}")
    captcha_input = page.locator('input[placeholder="请输入验证码"]')
    if captcha_input.is_visible():
        captcha_input.fill("")
        captcha_input.fill(captcha_text)
    else:
        logger.error("找不到验证码输入框")
        return RESULT_CAPTCHA_FAILED

    page.wait_for_timeout(300)

    # --- Step 8: 点击签到按钮 ---
    logger.info("点击签到按钮...")
    submit_btn = page.get_by_role("button", name="签到")
    if not safe_click(page, submit_btn, timeout=5000):
        logger.error("找不到签到提交按钮")
        return RESULT_ERROR

    # --- Step 9: 等待并判断签到结果 ---
    page.wait_for_timeout(2000)

    page_content = page.content()

    if "签到成功" in page_content:
        logger.info("✅ 签到成功！")
        return RESULT_OK
    elif "已签到" in page_content or "今日已签到" in page_content:
        logger.info("📌 今日已签到，无需重复签到")
        return RESULT_ALREADY
    elif "验证码错误" in page_content or "验证码不正确" in page_content:
        logger.warning("❌ 验证码错误")
        return RESULT_CAPTCHA_FAILED
    else:
        # 检查是否有奖励信息
        page_text = page.evaluate("document.body.innerText")
        logger.info(f"签到后页面文本: {page_text[:500]}")
        logger.info("✅ 签到操作已完成")
        return RESULT_OK


def login(page: Page) -> bool:
    """执行登录操作。返回是否登录成功。"""
    username, password = load_credentials()
    logger.info(f"登录用户: {username}")

    page.goto(LOGIN_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 填写用户名
    username_input = page.get_by_placeholder("Username")
    username_input.fill(username)

    # 填写密码
    password_input = page.get_by_placeholder("Password")
    password_input.fill(password)

    # 点击登录
    login_btn = page.get_by_role("button", name="登录")
    login_btn.click()
    page.wait_for_timeout(5000)

    # 确认登录成功（检查是否跳转到 dashboard）
    current_url = page.url
    if "/dashboard" in current_url:
        logger.info("✅ 登录成功")
        return True
    else:
        logger.error(f"❌ 登录失败，当前页面: {current_url}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="冲上云霄每日自动签到"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行（不显示浏览器窗口）",
    )
    parser.add_argument(
        "--browser-channel",
        type=str,
        default="msedge",
        help='浏览器通道，Windows 上默认 "msedge"，Ubuntu/GitHub Actions 上请设为 "chromium"',
    )
    parser.add_argument(
        "--result-file",
        type=str,
        help="将签到结果写入指定 JSON 文件（供 GitHub Actions 等使用）",
    )
    args = parser.parse_args()

    result = {
        "status": RESULT_ERROR,
        "message": "",
        "timestamp": datetime.now().isoformat(),
        "username": os.getenv("VPNPN_USERNAME", "unknown"),
    }

    # 加载凭据（同时确保 env 已加载）
    username, _ = load_credentials()
    result["username"] = username

    try:
        with sync_playwright() as p:
            # 根据 --browser-channel 选择浏览器
            browser_args = {
                "headless": args.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            }
            if args.browser_channel and args.browser_channel != "chromium":
                browser_args["channel"] = args.browser_channel

            browser = p.chromium.launch(**browser_args)

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                checkin_status = perform_checkin(page)
                result["status"] = checkin_status

                if checkin_status == RESULT_OK:
                    result["message"] = "签到成功"
                elif checkin_status == RESULT_ALREADY:
                    result["message"] = "今日已签到"
                elif checkin_status == RESULT_CAPTCHA_FAILED:
                    result["message"] = "验证码识别失败"
                else:
                    result["message"] = "签到执行异常"

            except Exception as e:
                logger.exception(f"签到过程异常: {e}")
                result["status"] = RESULT_ERROR
                result["message"] = str(e)

            finally:
                browser.close()

    except Exception as e:
        logger.exception(f"浏览器启动失败: {e}")
        result["status"] = RESULT_ERROR
        result["message"] = f"浏览器启动失败: {e}"

    # 输出结果
    logger.info(f"===== 签到结果: {result['message']} =====")

    # 写入结果文件
    if args.result_file:
        result_path = Path(args.result_file)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"结果已写入: {result_path}")

    # 非零状态码表示失败
    if result["status"] in (RESULT_ERROR, RESULT_CAPTCHA_FAILED):
        sys.exit(1)


if __name__ == "__main__":
    main()
