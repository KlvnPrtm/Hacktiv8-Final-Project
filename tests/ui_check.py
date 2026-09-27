"""Run with a Python environment containing Playwright + installed Chromium.

Starts the fixture with the project's .venv Python, then stops it automatically.
All responses and screenshots are explicitly labeled mock.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:5051'
SHOTS = ROOT / 'screenshots'


def run():
    SHOTS.mkdir(exist_ok=True)
    interpreter = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    process = subprocess.Popen([str(interpreter), str(ROOT / 'tests/demo_server.py')],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checks = []
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError('Demo fixture exited; check port 5051 is free.')
            try:
                with urlopen(URL, timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError('Demo fixture did not become ready.')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, permissions=['clipboard-read', 'clipboard-write'])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(URL)
            expect(page.locator('.demo-banner')).to_be_visible()
            expect(page.locator('#welcome')).to_be_visible()
            page.screenshot(path=str(SHOTS / '01-desktop-awal-mock.png'), full_page=True)
            page.locator('[data-prompt]').first.click()
            assert 'list' in page.locator('#message').input_value()
            assert page.locator('.message').count() == 0
            checks.append('Prompt starter fills composer without sending')
            page.locator('#message').press('Enter')
            expect(page.locator('.loading-message')).to_be_visible()
            expect(page.locator('#send')).to_be_disabled()
            expect(page.locator('[data-new-chat]').first).to_be_disabled()
            expect(page.locator('.assistant-message')).to_have_count(1)
            expect(page.locator('pre code').first).to_contain_text('nilai')
            page.locator('.code-copy').first.click()
            assert 'nilai' in page.evaluate('navigator.clipboard.readText()')
            page.locator('.copy-answer').first.click()
            assert 'Dictionary' in page.evaluate('navigator.clipboard.readText()')
            checks.append('Send, loading, duplicate prevention, Markdown, code copy, answer copy')
            page.screenshot(path=str(SHOTS / '02-desktop-percakapan-mock.png'), full_page=True)
            page.get_by_text('Detail', exact=True).click()
            page.locator('#message').fill('Beri contoh lainnya')
            with page.expect_request('**/api/chat') as outgoing:
                page.locator('#message').press('Enter')
            body = outgoing.value.post_data_json
            assert body['detail'] == 'detail' and len(body['history']) == 2
            expect(page.locator('.assistant-message')).to_have_count(2)
            checks.append('Follow-up contains completed history and selected detail mode')
            page.locator('[data-new-chat]').first.click()
            expect(page.locator('#reset-dialog')).to_be_visible()
            expect(page.get_by_role('button', name='Batal', exact=True)).to_be_focused()
            page.keyboard.press('Escape')
            expect(page.locator('.assistant-message')).to_have_count(2)
            page.locator('[data-new-chat]').first.click()
            page.get_by_role('button', name='Ya, chat baru').click()
            expect(page.locator('#welcome')).to_be_visible()
            checks.append('Reset confirmation, cancel default, Escape cancellation, confirmed reset')

            page.route('**/api/chat', lambda route: route.fulfill(status=429, content_type='application/json',
                body=json.dumps({'error': {'code': 'rate_limit', 'message': 'Kuota mock habis. Coba lagi.'}})), times=1)
            page.locator('#message').fill('Jelaskan list')
            page.locator('#send').click()
            expect(page.locator('.error-card')).to_be_visible()
            expect(page.locator('.user-message')).to_have_count(1)
            page.get_by_role('button', name='Coba lagi', exact=True).click()
            expect(page.locator('.assistant-message')).to_have_count(1)
            expect(page.locator('.user-message')).to_have_count(1)
            checks.append('429 error and retry without duplicate user turn')
            page.route('**/api/chat', lambda route: route.abort('failed'), times=1)
            page.locator('#message').fill('Pesan yang ingin diubah')
            page.locator('#send').click()
            expect(page.locator('.error-card')).to_be_visible()
            page.get_by_role('button', name='Ubah pesan').click()
            expect(page.locator('#message')).to_have_value('Pesan yang ingin diubah')
            expect(page.locator('.user-message')).to_have_count(1)
            checks.append('Network failure and edit recovery preserve completed history')
            page.locator('#message').fill('uji html <img src=x onerror="window.xss=3">')
            page.locator('#send').click()
            expect(page.locator('.assistant-message')).to_have_count(2)
            assert page.evaluate('window.xss') is None
            assert page.locator('.message-body script, .message-body img').count() == 0
            assert page.locator('.message-body a[href^="javascript:"]').count() == 0
            checks.append('User text and model HTML cannot execute script')
            page.reload()
            expect(page.locator('#welcome')).to_be_visible()
            assert page.locator('.message').count() == 0
            page.locator('#message').fill('a' * 4000)
            expect(page.locator('#char-count')).to_have_text('4.000 / 4.000')
            page.locator('#message').fill('baris satu')
            page.locator('#message').press('Shift+Enter')
            assert '\n' in page.locator('#message').input_value()
            checks.append('Refresh clears chat, long input counter, Shift+Enter newline')

            for width in [375, 768, 1024, 1440]:
                page.set_viewport_size({'width': width, 'height': 900})
                page.reload()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert page.locator('#send').bounding_box()['y'] < 900
            checks.append('No horizontal overflow at 375, 768, 1024, 1440 px; composer stays visible')
            mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                                         device_scale_factor=1, reduced_motion='reduce')
            phone = mobile.new_page()
            phone.goto(URL)
            phone.screenshot(path=str(SHOTS / '03-mobile-awal-mock.png'), full_page=True)
            phone.locator('[data-prompt]').first.click()
            phone.locator('#send').click()
            expect(phone.locator('.assistant-message')).to_have_count(1)
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
            phone.screenshot(path=str(SHOTS / '04-mobile-percakapan-mock.png'), full_page=True)
            checks.append('Mobile touch viewport, reduced motion, and conversation screenshot')
            assert not errors, errors
            checks.append('No uncaught browser JavaScript errors')
            browser.close()
        print(json.dumps({'passed': len(checks), 'checks': checks}, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == '__main__':
    run()
